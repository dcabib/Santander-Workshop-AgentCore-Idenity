import pytest

from santander_demo.aws_workshop.client import verify_target_headers
from santander_demo.aws_workshop.contracts import USER_TOKEN_HEADER


@pytest.mark.parametrize("headers", [
    [USER_TOKEN_HEADER],
    [USER_TOKEN_HEADER, "x-amzn-bedrock-agentcore-policy-session-id"],
    ["X-Amzn-Bedrock-AgentCore-Policy-Session-Id", USER_TOKEN_HEADER.lower()],
])
def test_service_policy_header_does_not_change_user_identity_contract(headers):
    verify_target_headers(headers)


@pytest.mark.parametrize("headers", [
    [],
    ["x-amzn-bedrock-agentcore-policy-session-id"],
    [USER_TOKEN_HEADER, "Authorization"],
    [USER_TOKEN_HEADER, "X-Other-Identity"],
    [USER_TOKEN_HEADER, USER_TOKEN_HEADER.lower()],
])
def test_missing_duplicated_or_unexpected_identity_headers_remain_blocked(headers):
    with pytest.raises(RuntimeError, match="UNEXPECTED_TARGET_HEADER_ALLOWLIST"):
        verify_target_headers(headers)
