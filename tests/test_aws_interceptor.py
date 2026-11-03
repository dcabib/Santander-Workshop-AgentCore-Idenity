import copy
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from infra.workshop.generate import backend, gateway
from santander_demo.aws_workshop.contracts import USER_TOKEN_HEADER
from santander_demo.aws_workshop.identity import verify
from santander_demo.aws_workshop.interceptor import transform


@pytest.fixture
def interceptor_request():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = {"issuer": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test",
              "clients": ["supervisor"]}
    claims = {"iss": config["issuer"], "sub": "c", "aud": "supervisor", "token_use": "id",
              "email_verified": True, "iat": datetime.now(UTC),
              "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(claims, key, algorithm="RS256")
    event = {"interceptorInputVersion": "1.0", "mcp": {"gatewayRequest": {
        "headers": {"authorization": "Bearer " + token, "x-user": "attacker"},
        "body": {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": "especialista___consultar_fraude",
                            "arguments": {"cliente_id": "C001"}}},
    }}}
    return event, config, key


def verified(key):
    return lambda token, config: verify(token, config, key=key.public_key())


@pytest.mark.parametrize("name", [
    "especialista___consultar_fraude",
    "transaction___especialista___consultar_tabela",
    "retail___riscos___consultar_risco",
])
def test_interceptor_forwards_only_verified_authorization_to_declared_tools(interceptor_request, name):
    event, config, key = interceptor_request
    event["mcp"]["gatewayRequest"]["body"]["params"]["name"] = name
    before = copy.deepcopy(event)
    result = transform(event, config, verified(key))["mcp"]["transformedGatewayRequest"]
    assert result["body"] == event["mcp"]["gatewayRequest"]["body"]
    expected = USER_TOKEN_HEADER if name.startswith("especialista___") else "Authorization"
    assert result["headers"] == {
        expected: event["mcp"]["gatewayRequest"]["headers"]["authorization"],
    }
    assert event == before


@pytest.mark.parametrize("failure", ["expired", "signature", "audience", "duplicate", "missing", "newline"])
def test_interceptor_fails_closed_for_invalid_identity(interceptor_request, failure):
    event, config, key = interceptor_request
    headers = event["mcp"]["gatewayRequest"]["headers"]
    if failure == "signature":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif failure == "audience":
        config["clients"] = ["other"]
    elif failure == "expired":
        claims = jwt.decode(headers["authorization"][7:], key.public_key(),
                            algorithms=["RS256"], audience="supervisor")
        headers["authorization"] = "Bearer " + jwt.encode(
            {**claims, "exp": datetime.now(UTC) - timedelta(seconds=1)}, key, algorithm="RS256",
        )
    elif failure == "duplicate":
        headers["Authorization"] = headers["authorization"]
    elif failure == "missing":
        del headers["authorization"]
    elif failure == "newline":
        headers["authorization"] += "\n"
    with pytest.raises((ValueError, jwt.InvalidTokenError)):
        transform(event, config, verified(key))


def test_interceptor_never_propagates_to_an_unlisted_target(interceptor_request):
    event, config, _ = interceptor_request
    event["mcp"]["gatewayRequest"]["body"]["params"]["name"] = "attacker___collect"
    check = Mock()
    with pytest.raises(ValueError, match="UNTRUSTED_PROPAGATION_TARGET"):
        transform(event, config, check)
    check.assert_not_called()


def test_lambda_target_does_not_receive_human_bearer(interceptor_request):
    event, config, _ = interceptor_request
    event["mcp"]["gatewayRequest"]["body"]["params"]["name"] = "riscos___consultar_risco"
    assert "headers" not in transform(event, config)["mcp"]["transformedGatewayRequest"]


def test_iac_keeps_gateway_jwt_policy_and_runtime_sigv4_boundary():
    resources = gateway()["Resources"]
    properties = resources["Gateway"]["Properties"]
    assert properties["AuthorizerType"] == "CUSTOM_JWT"
    assert properties["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
    assert properties["InterceptorConfigurations"][0]["Interceptor"]["Lambda"]["Arn"] == {
        "Fn::GetAtt": ["Interceptor", "Arn"],
    }
    runtime = backend()["Resources"]["Runtime"]["Properties"]
    assert "AuthorizerConfiguration" not in runtime
    assert runtime["RequestHeaderConfiguration"]["RequestHeaderAllowlist"] == [USER_TOKEN_HEADER]
    assert backend()["Resources"]["RuntimeBoundary"]["Properties"]["GatewayRoleArn"] == {
        "Ref": "GatewayRoleArn",
    }


def test_interceptor_overwrites_spoofed_user_header_with_the_verified_bearer(interceptor_request):
    event, config, key = interceptor_request
    event["mcp"]["gatewayRequest"]["headers"][USER_TOKEN_HEADER.lower()] = "Bearer attacker"
    result = transform(event, config, verified(key))["mcp"]["transformedGatewayRequest"]
    assert result["headers"] == {
        USER_TOKEN_HEADER: event["mcp"]["gatewayRequest"]["headers"]["authorization"],
    }
