"""Identidades do sandbox inteiramente AWS; nenhum usuário precisa existir antes."""

import hashlib
import json
import re

import jwt

from santander_demo.identity import Identity
from santander_demo.rag.contract import TOOL


def issuer(config):
    pool = config["user_pool_id"]
    if not re.fullmatch(re.escape(config["region"]) + r"_[A-Za-z0-9]+", pool):
        raise ValueError("INVALID_COGNITO_POOL")
    return f"https://cognito-idp.{config['region']}.amazonaws.com/{pool}"


def verify(token, config, key=None):
    url = issuer(config)
    key = (
        key
        or jwt.PyJWKClient(url + "/.well-known/jwks.json", timeout=15)
        .get_signing_key_from_jwt(token)
        .key
    )
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        issuer=url,
        audience=config["login_client_id"],
        options={"require": ["exp", "iat", "iss", "aud", "sub", "email", "token_use"]},
    )
    if claims["token_use"] != "id" or claims.get("email_verified") is not True:
        raise ValueError("VERIFIED_COGNITO_ID_TOKEN_REQUIRED")
    # Aliases internos apenas para reutilizar o contrato local; o Cedar usa sub/iss originais.
    return Identity({**claims, "tid": config["user_pool_id"], "oid": claims["sub"]})


def user_ref(identity):
    return hashlib.sha256(
        f"{identity.claims['iss']}:{identity.claims['sub']}".encode()
    ).hexdigest()[:12]


def policies(gateway_arn, pool_issuer, app_client_id, users):
    def literal(value):
        return json.dumps(value)

    result = {}
    for label in "abc":
        claims = {
            "iss": pool_issuer,
            "aud": app_client_id,
            "token_use": "id",
            "email": users[label]["email"],
            "email_verified": "true",
        }
        predicates = [
            f"principal.hasTag({literal(k)}) && principal.getTag({literal(k)}) == {literal(v)}"
            for k, v in claims.items()
        ]
        predicates.append("context.input has userContext")
        predicates.append("context.input.userContext.userId == " + literal(users[label]["email"]))
        result["AllowUser" + label.upper()] = (
            "permit(\n"
            f"  principal == AgentCore::OAuthUser::{literal(users[label]['oid'])},\n"
            f"  action == AgentCore::Action::{literal(TOOL)},\n"
            f"  resource == AgentCore::Gateway::{literal(gateway_arn)}\n"
            ") when {\n  " + " &&\n  ".join(predicates) + "\n};"
        )
    # D não recebe permit: a decisão padrão do Cedar é DENY.
    return result


def login(session, config, environment, label):
    """Senhas sintéticas vêm do Secrets Manager; nunca são impressas nem persistidas localmente."""
    if label not in "abcd" or len(label) != 1:
        raise ValueError("UNKNOWN_USER")
    credential = json.loads(
        session.client("secretsmanager").get_secret_value(
            SecretId=environment[f"User{label.upper()}SecretArn"]
        )["SecretString"]
    )
    response = session.client("cognito-idp").initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=config["login_client_id"],
        AuthParameters={"USERNAME": credential["username"], "PASSWORD": credential["password"]},
    )
    token = response.get("AuthenticationResult", {}).get("IdToken")
    if not token:
        raise ValueError("COGNITO_LOGIN_CHALLENGE_OR_FAILURE")
    identity = verify(token, config)
    expected = config["users"][label]
    if identity.claims["sub"] != expected["oid"] or identity.claims["email"] != expected["email"]:
        raise ValueError("COGNITO_LOGIN_WRONG_USER")
    return token
