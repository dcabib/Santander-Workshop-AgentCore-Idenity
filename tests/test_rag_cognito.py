import copy
import json
import time
from unittest.mock import MagicMock
from uuid import uuid4

import cedarpy
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from infra.rag.generate import generate
from santander_demo.rag import client, cognito, cognito_seed
from santander_demo.rag.contract import TOOL
from santander_demo.rag.corpus import allowed_documents
from santander_demo.rag.local import LOCAL_GATEWAY, LOCAL_USERS, LocalCognitoRagLab


@pytest.fixture
def config():
    return {
        "project": "test-rag",
        "profile": "default",
        "region": "us-east-1",
        "account_id": "111111111111",
        "auth_provider": "cognito",
        "user_pool_id": "us-east-1_Example123",
        "login_client_id": "abc123",
        "caller_principal_arn": "arn:aws:iam::111111111111:role/Notebook",
        "model_arn": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
        "users": copy.deepcopy(LOCAL_USERS),
    }


def claims(config, label):
    return {
        "iss": cognito.issuer(config),
        "aud": config["login_client_id"],
        "token_use": "id",
        "sub": config["users"][label]["oid"],
        "email": config["users"][label]["email"],
        "email_verified": True,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }


def allowed(config, data, email):
    p = {"type": "AgentCore::OAuthUser", "id": data["sub"]}
    tags = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in data.items()}
    return cedarpy.is_authorized(
        {
            "principal": p,
            "action": {"type": "AgentCore::Action", "id": TOOL},
            "resource": {"type": "AgentCore::Gateway", "id": LOCAL_GATEWAY},
            "context": {"input": {"userContext": {"userId": email}}},
        },
        "\n".join(
            cognito.policies(
                LOCAL_GATEWAY, cognito.issuer(config), config["login_client_id"], config["users"]
            ).values()
        ),
        [{"uid": p, "attrs": {}, "parents": [], "tags": tags}],
    ).allowed


@pytest.mark.parametrize("label", "abcd")
@pytest.mark.parametrize("other", "abcd")
def test_cognito_policy_binds_subject_and_verified_email(config, label, other):
    assert allowed(config, claims(config, label), config["users"][other]["email"]) == (
        label == other and label != "d"
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("iss", "https://attacker.invalid"),
        ("aud", "other"),
        ("token_use", "access"),
        ("email_verified", False),
        ("sub", str(uuid4())),
    ],
)
def test_changed_cognito_claims_do_not_authorize(config, key, value):
    data = claims(config, "a")
    data[key] = value
    assert not allowed(config, data, config["users"]["a"]["email"])


def test_cognito_signature_issuer_audience_and_expiry_are_verified(config):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    data = claims(config, "a")
    token = jwt.encode(data, key, algorithm="RS256")
    assert cognito.verify(token, config, key.public_key()).claims["oid"] == data["sub"]
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidSignatureError):
        cognito.verify(jwt.encode(data, attacker, algorithm="RS256"), config, key.public_key())
    for claim, val in [("exp", 1), ("aud", "other"), ("iss", "https://other.invalid")]:
        with pytest.raises(jwt.InvalidTokenError):
            cognito.verify(
                jwt.encode({**data, claim: val}, key, algorithm="RS256"), config, key.public_key()
            )
    client.validate_config(config)


def test_iac_creates_four_users_without_email_delivery_or_plaintext_credentials(tmp_path):
    docs = generate(tmp_path)
    r = docs["identity"]["Resources"]
    assert len([v for v in r.values() if v["Type"] == "AWS::Cognito::UserPoolUser"]) == 4
    for label in "ABCD":
        assert r[f"User{label}"]["Properties"]["MessageAction"] == "SUPPRESS"
        assert r[f"Secret{label}"]["Properties"]["GenerateSecretString"]["PasswordLength"] == 32
    assert not docs["access-cognito"]["Resources"].get("OAuth")
    assert "OAuthProviderName" not in docs["access-cognito"]["Outputs"]
    assert (
        docs["access-cognito"]["Resources"]["Gateway"]["Properties"]["PolicyEngineConfiguration"][
            "Mode"
        ]
        == "ENFORCE"
    )


def test_cfn_user_password_initializer_is_idempotent_and_delete_does_not_recreate_users():
    event = {
        "RequestType": "Create",
        "ResourceProperties": {
            "UserPoolId": "pool",
            **{f"User{x}SecretArn": f"secret-{x}" for x in "ABCD"},
        },
    }
    api, secrets = MagicMock(), MagicMock()
    secrets.get_secret_value.return_value = {
        "SecretString": '{"username":"test","password":"hidden"}'
    }
    api.admin_get_user.return_value = {"UserAttributes": [{"Name": "sub", "Value": str(uuid4())}]}
    assert set(cognito_seed.provision(event, api, secrets)) == {f"User{x}Oid" for x in "ABCD"}
    assert api.admin_set_user_password.call_count == 4
    event["RequestType"] = "Delete"
    assert cognito_seed.provision(event, api, secrets) == {}
    assert api.admin_set_user_password.call_count == 4


@pytest.mark.parametrize("label", "abcd")
def test_offline_cognito_lab_exercises_same_signed_claims_and_policy(label):
    lab = LocalCognitoRagLab()
    result = lab.call(label)
    assert set(result["document_ids"]) == allowed_documents(label)
    assert result["retrieval_calls"] == result["generation_calls"] == (label != "d")
    assert lab.call("a", forged_email=LOCAL_USERS["c"]["email"])["policy"] == "DENY"
