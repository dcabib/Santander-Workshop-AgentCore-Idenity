"""Cognito: validação criptográfica e login das identidades sintéticas do IaC."""

import base64
import hashlib
import hmac
import json
from functools import lru_cache

import jwt


@lru_cache(maxsize=8)
def keys(issuer):
    return jwt.PyJWKClient(issuer + "/.well-known/jwks.json", timeout=15)


def verify(token, config, *, key=None):
    issuer = config["issuer"]
    claims = jwt.decode(
        token,
        key or keys(issuer).get_signing_key_from_jwt(token).key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=config["clients"],
        options={"require": ["exp", "iat", "iss", "aud", "sub", "token_use"]},
    )
    if claims["token_use"] != "id" or claims.get("email_verified") is not True:
        raise ValueError("VERIFIED_COGNITO_ID_TOKEN_REQUIRED")
    return claims


def actor(claims):
    return hashlib.sha256(f"{claims['iss']}:{claims['sub']}".encode()).hexdigest()


def login(aws, outputs, user="c", application="supervisor"):
    if user not in {"a", "b", "c", "d"}:
        raise ValueError("UNKNOWN_WORKSHOP_USER")
    if application not in {"supervisor", "riscos"}:
        raise ValueError("UNKNOWN_WORKSHOP_APPLICATION")
    secrets = aws.client("secretsmanager")
    credential = json.loads(secrets.get_secret_value(
        SecretId=outputs[f"User{user.upper()}SecretArn"]
    )["SecretString"])
    app = json.loads(secrets.get_secret_value(
        SecretId=outputs[application.title() + "SecretArn"]
    )["SecretString"])
    secret_hash = base64.b64encode(hmac.new(
        app["client_secret"].encode(),
        (credential["username"] + app["client_id"]).encode(),
        hashlib.sha256,
    ).digest()).decode()
    result = aws.client("cognito-idp").initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=app["client_id"],
        AuthParameters={
            "USERNAME": credential["username"],
            "PASSWORD": credential["password"],
            "SECRET_HASH": secret_hash,
        },
    )
    token = result.get("AuthenticationResult", {}).get("IdToken")
    if not token:
        raise ValueError("COGNITO_LOGIN_CHALLENGE_OR_FAILURE")
    claims = verify(token, {
        "issuer": outputs["Issuer"],
        "clients": [outputs[application.title() + "ClientId"]],
    })
    if claims["sub"] != outputs[f"User{user.upper()}Oid"]:
        raise ValueError("COGNITO_LOGIN_WRONG_USER")
    return token
