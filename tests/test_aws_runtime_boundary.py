"""Regressão: Gateway como entrada obrigatória e JWT humano verificado na fonte."""

import json
from unittest.mock import Mock

import pytest

from infra.workshop.generate import bindings, gateway
from santander_demo.aws_workshop import backend
from santander_demo.aws_workshop.contracts import USER_TOKEN_HEADER
from santander_demo.aws_workshop.runtime_boundary import policy, provision

RUNTIME = "arn:aws:bedrock-agentcore:us-east-1:111111111111:runtime/workshop-source"
ROLE = "arn:aws:iam::111111111111:role/workshop-gateway"


@pytest.mark.parametrize("runtime,role", [
    (RUNTIME + "*", ROLE),
    (RUNTIME.replace("us-east-1", "us-west-2"), ROLE),
    (RUNTIME, ROLE.replace("111111111111", "222222222222")),
    (RUNTIME, "*"),
])
def test_boundary_cannot_target_a_wildcard_or_cross_account_role(runtime, role):
    with pytest.raises(ValueError, match="EXACT_RUNTIME"):
        policy(runtime, role)


def test_resource_policy_denies_other_principals_even_with_identity_permissions():
    statements = policy(RUNTIME, ROLE)["Statement"]
    allow, deny = statements
    assert allow["Principal"] == {"AWS": ROLE}
    assert allow["Action"] == "bedrock-agentcore:InvokeAgentRuntime"
    assert deny["Principal"] == {"AWS": "*"} and deny["Effect"] == "Deny"
    assert set(deny["Action"]) == {
        "bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:InvokeAgentRuntimeForUser",
    }
    assert deny["Condition"] == {"ArnNotEquals": {"aws:PrincipalArn": ROLE}}
    assert all(item["Resource"] == RUNTIME for item in statements)


def event(operation):
    return {"RequestType": operation, "ResourceProperties": {
        "RuntimeArn": RUNTIME, "GatewayRoleArn": ROLE,
    }}


def test_provider_verifies_the_deployed_policy():
    control = Mock()
    control.get_resource_policy.return_value = {"policy": json.dumps(policy(RUNTIME, ROLE))}
    assert provision(event("Update"), control) == {"Boundary": "GATEWAY_ROLE_ONLY"}
    control.put_resource_policy.assert_called_once_with(
        resourceArn=RUNTIME, policy=json.dumps(policy(RUNTIME, ROLE)),
    )
    control.get_resource_policy.assert_called_once_with(resourceArn=RUNTIME)


def test_provider_rejects_an_incomplete_readback():
    control = Mock()
    control.get_resource_policy.return_value = {"policy": json.dumps({
        "Version": "2012-10-17", "Statement": policy(RUNTIME, ROLE)["Statement"][:1],
    })}
    with pytest.raises(ValueError, match="READBACK_MISMATCH"):
        provision(event("Create"), control)


def test_delete_keeps_the_boundary_until_the_runtime_itself_is_deleted():
    control = Mock()
    assert provision(event("Delete"), control)["Boundary"] == "PRESERVED_UNTIL_RUNTIME_DELETION"
    assert not control.mock_calls


def test_backend_uses_only_the_user_header_and_still_verifies_its_jwt(monkeypatch):
    verify = Mock(return_value={"sub": "signed-person"})
    monkeypatch.setattr(backend, "verify", verify)
    assert backend.verified_source_claims({
        USER_TOKEN_HEADER.lower(): "Bearer verified-jwt", "authorization": "AWS4-HMAC-SHA256...",
    }, {"issuer": "configured"}) == {"sub": "signed-person"}
    verify.assert_called_once_with("verified-jwt", {"issuer": "configured"})


def test_authorization_header_cannot_replace_the_required_human_jwt():
    with pytest.raises(ValueError, match="USER_BEARER_REQUIRED"):
        backend.verified_source_claims({"authorization": "Bearer caller"}, {})


def test_gateway_iam_signature_and_user_header_are_configured_separately():
    document = bindings()
    target = document["Resources"]["Target"]["Properties"]
    assert target["CredentialProviderConfigurations"] == [{
        "CredentialProviderType": "GATEWAY_IAM_ROLE",
        "CredentialProvider": {"IamCredentialProvider": {
            "Service": "bedrock-agentcore", "Region": {"Ref": "AWS::Region"},
        }},
    }]
    assert target["MetadataConfiguration"]["AllowedRequestHeaders"] == [USER_TOKEN_HEADER]
    grant = document["Resources"]["GatewayRuntimeAccess"]["Properties"]
    assert grant["Roles"] == [{"Ref": "GatewayRoleName"}]
    assert grant["PolicyDocument"]["Statement"][0]["Resource"] == [
        {"Ref": "RuntimeArn"}, {"Fn::Sub": "${RuntimeArn}/runtime-endpoint/*"},
    ]
    trust = gateway()["Resources"]["GatewayRole"]["Properties"]["AssumeRolePolicyDocument"]
    assert trust["Statement"][0]["Condition"]["ArnLike"]["aws:SourceArn"]["Fn::If"][:2] == [
        "HasKnownGateway", {"Ref": "KnownGatewayArn"},
    ]
