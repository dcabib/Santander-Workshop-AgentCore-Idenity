"""Integração SDK: escopo IAM, retomada, configuração do target e Cedar."""

from types import SimpleNamespace
from unittest.mock import patch

import cedarpy
import pytest

from scripts.sdk_notebook_lessons import build_cleanup, build_integration
from tests.test_sdk_gateway import ACCOUNT, REGION, provisioning_cells
from tests.test_sdk_policy import PolicyAWS, policy_setup


class IntegrationAWS(PolicyAWS):
    def respond(self, service, method, args):
        if method == "get_agent_runtime":
            return self.objects["runtime"]
        if method == "list_tags_for_resource" and args["resourceArn"] == self.objects.get("runtime", {}).get("agentRuntimeArn"):
            return {"tags": self.objects["runtime"]["tags"]}
        if method == "create_gateway_target" and "mcpServer" in args["targetConfiguration"]["mcp"]:
            self.objects["runtime_target"] = {
                **args, "targetId": "runtime-abcdefghij", "status": "READY",
                "ResponseMetadata": {"RequestId": "target-request"},
            }
            return self.objects["runtime_target"]
        if method == "get_gateway_target" and args["targetId"] == "runtime-abcdefghij":
            if "runtime_target" not in self.objects:
                self.not_found(method)
            return self.objects["runtime_target"]
        if method == "delete_gateway_target" and args["targetId"] == "runtime-abcdefghij":
            del self.objects["runtime_target"]
            return {}
        result = super().respond(service, method, args)
        if method in {"create_policy", "get_policy"}:
            result = {**result, "ResponseMetadata": {"RequestId": "policy-request"}}
        return result


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='integration-test'\n")
    monkeypatch.chdir(tmp_path)
    aws = IntegrationAWS()
    namespace = {}
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-request"})
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied), patch("time.sleep"):
        for source in provisioning_cells():
            exec(source, namespace)
    namespace = policy_setup(aws)
    state = namespace["state"]
    arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/test-abcdefghij"
    role_arn = f"arn:aws:iam::{ACCOUNT}:role/{state.prefix}-runtime"
    aws.objects["runtime"] = {
        "agentRuntimeArn": arn, "agentRuntimeId": "test-abcdefghij",
        "roleArn": role_arn, "protocolConfiguration": {"serverProtocol": "MCP"},
        "status": "READY", "tags": state.tags,
    }
    state.record("runtime.instance", {"arn": arn, "id": "test-abcdefghij", "role_arn": role_arn}, lesson="03")
    return aws


def run_setup(aws):
    namespace = {}
    with patch("boto3.Session", return_value=aws), patch("time.sleep"):
        for cell in build_integration().cells:
            if cell.cell_type != "code":
                continue
            if "jwks = jwt.PyJWKClient" in cell.source:
                break
            exec(cell.source, namespace)
    return namespace


def test_integration_limits_gateway_permission_and_resumes_without_writes(workspace):
    namespace = run_setup(workspace)
    permission = namespace["state"].get("gateway.runtime_permission")
    document = workspace.objects["role_policies"][permission["role_name"], permission["name"]]
    assert document["Statement"] == [{
        "Effect": "Allow", "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
        "Resource": [namespace["runtime_entry"]["arn"], namespace["runtime_entry"]["arn"] + "/runtime-endpoint/DEFAULT"],
    }]
    assert namespace["TARGET_CREDENTIALS"][0]["credentialProvider"]["iamCredentialProvider"] == {
        "service": "bedrock-agentcore", "region": REGION,
    }
    created = [args for _, method, args in workspace.calls if method == "create_policy"][-1]
    assert created["validationMode"] == "FAIL_ON_ANY_FINDINGS"
    assert created["enforcementMode"] == "ACTIVE"
    count = len(workspace.calls)
    run_setup(workspace)
    assert not any(method.startswith(("put_", "create_", "update_")) for _, method, _ in workspace.calls[count:])


@pytest.mark.parametrize("drift", ["permission", "target"])
def test_integration_refuses_unexpected_changes(workspace, drift):
    namespace = run_setup(workspace)
    if drift == "permission":
        permission = namespace["state"].get("gateway.runtime_permission")
        workspace.objects["role_policies"][permission["role_name"], permission["name"]]["Statement"][0]["Resource"] = "*"
    else:
        workspace.objects["runtime_target"]["targetConfiguration"]["mcp"]["mcpServer"]["endpoint"] = "https://unexpected.invalid"
    count = len(workspace.calls)
    with pytest.raises(AssertionError):
        run_setup(workspace)
    assert not any(method.startswith(("put_", "create_", "update_")) for _, method, _ in workspace.calls[count:])


@pytest.mark.parametrize("changed", [None, "person", "issuer", "audience", "tool", "gateway"])
def test_workload_policy_only_allows_expected_person_and_operation(workspace, changed):
    namespace = run_setup(workspace)
    subject = namespace["analyst_entry"]["sub"] if changed != "person" else "another-person"
    tags = {"iss": namespace["ISSUER"], "aud": namespace["CLIENT_ID"], "token_use": "id"}
    if changed == "issuer":
        tags["iss"] = "https://unexpected.invalid"
    if changed == "audience":
        tags["aud"] = "another-client"
    principal = {"type": "AgentCore::OAuthUser", "id": subject}
    action = {"type": "AgentCore::Action", "id": namespace["TOOL_NAME"] if changed != "tool" else "another_tool"}
    resource = {"type": "AgentCore::Gateway", "id": namespace["gateway_entry"]["arn"] if changed != "gateway" else "another_gateway"}
    decision = cedarpy.is_authorized(
        {"principal": principal, "action": action, "resource": resource, "context": {}},
        namespace["CEDAR"],
        [{"uid": principal, "attrs": {}, "parents": [], "tags": tags}],
    )
    assert decision.allowed == (changed is None)


def test_cleanup_deletes_runtime_target_before_server(workspace):
    namespace = run_setup(workspace)
    namespace["wait_deleted"] = lambda read, not_found: None
    cleanup_cells = build_cleanup().cells
    target_index = next(i for i, c in enumerate(cleanup_cells) if c.cell_type == "code" and 'entry = state.get("gateway.runtime_target")' in c.source and "control.delete_gateway_target(" in c.source)
    runtime_index = next(
        i for i, c in enumerate(cleanup_cells)
        if c.cell_type == "code" and "control.delete_agent_runtime(" in c.source
        and 'entry = state.get("runtime.instance")' in c.source
    )
    assert target_index < runtime_index
    exec(cleanup_cells[target_index].source, namespace)
    assert namespace["state"].get("gateway.runtime_target") is None
    assert "runtime_target" not in workspace.objects
