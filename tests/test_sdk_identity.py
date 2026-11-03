"""A audiência é verificada depois da assinatura, sem implementar OBO fictício."""

import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts.sdk_notebook_lessons import build_identity
from tests.test_sdk_gateway import AWSContract, provisioning_cells


def identity_cells():
    for cell in build_identity().cells:
        if cell.cell_type == "code":
            if "async with httpx.AsyncClient" in cell.source:
                break
            yield cell.source


def test_same_subject_different_audiences_and_tampered_signature(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    monkeypatch.chdir(tmp_path)
    aws = AWSContract()
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "auth-test"})
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    original_response = aws.respond

    def response(service, method, args):
        if method == "initiate_auth":
            username = args["AuthParameters"]["USERNAME"]
            password = json.loads(aws.objects["secret"]["SecretString"])[username]
            assert args["AuthParameters"]["PASSWORD"] == password
            person = aws.objects["users"][username]
            claims = {
                "sub": next(a["Value"] for a in person["Attributes"] if a["Name"] == "sub"),
                "iss": f"https://cognito-idp.{aws.region_name}.amazonaws.com/{aws.objects['pool']['Id']}",
                "aud": args["ClientId"], "token_use": "id", "cognito:username": username,
                "iat": int(time.time()), "exp": int(time.time()) + 600,
            }
            return {"AuthenticationResult": {"IdToken": jwt.encode(claims, private_key, algorithm="RS256")}}
        return original_response(service, method, args)

    aws.respond = response
    jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=private_key.public_key()))
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied):
        namespace = {}
        for source in provisioning_cells():
            exec(source, namespace)
    call_count = len(aws.calls)
    identity_denied = httpx.Response(
        403, headers={"x-amzn-requestid": "identity-auth-test"},
        json={"jsonrpc": "2.0", "id": 0, "error": {
            "code": -32002, "message": "insufficient_scope - Not authorized",
        }},
    )
    with (
        patch("boto3.Session", return_value=aws),
        patch("httpx.post", return_value=identity_denied) as post,
        patch("jwt.PyJWKClient", return_value=jwks),
    ):
        for _run in range(2):
            namespace = {}
            for source in identity_cells():
                exec(source, namespace)
            claims = namespace["verified_claims"]
            assert claims["notebook"]["sub"] == claims["other_app"]["sub"]
            assert claims["notebook"]["aud"] != claims["other_app"]["aud"]
            # O primeiro JWT é válido para a outra aplicação.
            wrong_audience = post.call_args_list[-2].kwargs["headers"]["Authorization"].removeprefix("Bearer ")
            with pytest.raises(jwt.InvalidAudienceError):
                jwt.decode(
                    wrong_audience, private_key.public_key(), algorithms=["RS256"],
                    issuer=namespace["ISSUER"], audience=namespace["CLIENT_ID"],
                )
            # Alterar a audiência sem uma nova assinatura precisa invalidar o JWT.
            tampered = post.call_args_list[-1].kwargs["headers"]["Authorization"].removeprefix("Bearer ")
            with pytest.raises(jwt.InvalidSignatureError):
                jwt.decode(
                    tampered, private_key.public_key(), algorithms=["RS256"],
                    issuer=namespace["ISSUER"], audience=namespace["CLIENT_ID"],
                )
            assert "IdToken" not in namespace["state"].path.read_text()
    mutations = [
        method for _, method, _ in aws.calls[call_count:]
        if method.startswith(("create_", "update_", "put_", "admin_"))
    ]
    assert mutations == ["create_user_pool_client"]


@pytest.mark.parametrize("status,body,headers", [
    (200, {"result": {}}, {"x-amzn-requestid": "unexpected-success"}),
    (500, {"error": {"code": -32603}}, {"x-amzn-requestid": "service-error"}),
    (403, {"error": {"code": -32000, "message": "insufficient_scope"}}, {"x-amzn-requestid": "other-error"}),
    (403, {"error": {"code": -32002, "message": "different error"}}, {"x-amzn-requestid": "other-message"}),
    (403, {"error": {"code": -32002, "message": "insufficient_scope"}}, {}),
])
def test_identity_does_not_count_unrelated_failures_as_authorization_denial(status, body, headers):
    source = next(
        cell.source for cell in build_identity().cells
        if cell.cell_type == "code" and '"valid_signature_wrong_audience"' in cell.source
    )
    namespace = {
        "json": json, "httpx": httpx,
        "tokens": {"other_app": "test.payload.signature"},
        "verified_claims": {"other_app": {"aud": "other"}},
        "CLIENT_ID": "allowed", "GATEWAY_URL": "https://example.invalid/mcp",
    }
    with patch("httpx.post", return_value=httpx.Response(status, json=body, headers=headers)):
        with pytest.raises(AssertionError):
            exec(source, namespace)
