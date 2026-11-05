"""Contratos Policy, decisões Cedar reais e falhas que não comprovam negação."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import cedarpy
import httpx
import pytest

from scripts.sdk_notebook_lessons import build_cleanup, build_policy
from tests.test_sdk_gateway import ACCOUNT, REGION, AWSContract, provisioning_cells


class PolicyAWS(AWSContract):
    def respond(self, service, method, args):
        objects = self.objects
        if method == "create_policy_engine":
            objects["engine"] = {
                **args, "policyEngineId": "engine-abcdefghij", "status": "ACTIVE",
                "policyEngineArn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:policy-engine/engine-abcdefghij",
            }
        if method in {"create_policy_engine", "get_policy_engine"}:
            if "engine" not in objects:
                self.not_found(method)
            return objects["engine"]
        if method == "create_policy":
            objects["policy"] = {
                **args, "policyId": "policy-abcdefghij", "status": "ACTIVE",
                "policyArn": objects["engine"]["policyEngineArn"] + "/policy/policy-abcdefghij",
            }
        if method in {"create_policy", "get_policy"}:
            if "policy" not in objects:
                self.not_found(method)
            return objects["policy"]
        if method == "list_policies":
            return {"policies": [objects["policy"]]} if "policy" in objects else {"policies": []}
        if method == "update_gateway":
            objects["gateway"].update(args)
            return objects["gateway"]
        if method == "list_tags_for_resource" and args["resourceArn"] == objects.get("engine", {}).get("policyEngineArn"):
            return {"tags": objects["engine"]["tags"]}
        if method == "list_gateway_targets":
            return {"items": [objects["target"]]}
        if method == "list_attached_role_policies":
            return {"AttachedPolicies": []}
        if method == "list_role_policies":
            return {"PolicyNames": [name for role, name in objects["role_policies"] if role == args["RoleName"]]}
        if method == "delete_policy":
            assert "gateway" not in objects, "Delete consumer first"
            del objects["policy"]
            return {}
        if method == "delete_policy_engine":
            assert "policy" not in objects
            del objects["engine"]
            return {}
        return super().respond(service, method, args)

    def not_found(self, method):
        raise self.clients["bedrock-agentcore-control"].exceptions.ResourceNotFoundException(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
        )


def policy_setup(aws):
    namespace = {}
    with patch("boto3.Session", return_value=aws), patch("time.sleep"):
        for cell in build_policy().cells:
            if cell.cell_type != "code":
                continue
            if "jwks = jwt.PyJWKClient" in cell.source:
                break
            exec(cell.source, namespace)
    return namespace


@pytest.fixture
def policy_workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='policy-test'\n")
    monkeypatch.chdir(tmp_path)
    aws = PolicyAWS()
    namespace = {}
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    with (
        patch("boto3.Session", return_value=aws),
        patch("httpx.post", return_value=denied), patch("time.sleep"),
    ):
        for source in provisioning_cells():
            exec(source, namespace)
    return aws


def test_policy_sdk_creates_then_resumes_without_mutations(policy_workspace):
    aws = policy_workspace
    first = policy_setup(aws)
    count = len(aws.calls)
    second = policy_setup(aws)
    assert first["engine_entry"] == second["engine_entry"]
    assert first["policy_entry"] == second["policy_entry"]
    assert not [method for _, method, _ in aws.calls[count:] if method.startswith(("create_", "update_", "put_"))]
    call = next(args for _, method, args in aws.calls if method == "create_policy")
    assert call["validationMode"] == "FAIL_ON_ANY_FINDINGS"
    assert call["enforcementMode"] == "ACTIVE"
    update = next(args for _, method, args in aws.calls if method == "update_gateway")
    assert update["authorizerType"] == "CUSTOM_JWT"
    assert update["policyEngineConfiguration"]["mode"] == "ENFORCE"
    assert update["authorizerConfiguration"] == aws.objects["gateway"]["authorizerConfiguration"]
    statements = second["policy_iam"]["Statement"]
    assert all("*" not in str(statement["Resource"]) for statement in statements)
    assert set(statements[1]["Resource"]) == {
        second["engine_entry"]["arn"], second["gateway_entry"]["arn"],
    }


@pytest.mark.parametrize("person,customer,changes,want", [
    ("analista", "cliente-001", {}, True),
    ("analista", "cliente-002", {}, False),
    ("auditor", "cliente-001", {}, False),
    ("analista", "cliente-001", {"iss": "https://other.invalid"}, False),
    ("analista", "cliente-001", {"aud": "other-app"}, False),
    ("analista", "cliente-001", {"token_use": "access"}, False),
    ("analista", "cliente-001", {"aud": None}, False),
])
def test_cedar_checks_person_customer_and_verified_claims(policy_workspace, person, customer, changes, want):
    namespace = policy_setup(policy_workspace)
    user = namespace["state"].require("identity.user." + person, lesson="01")
    principal = {"type": "AgentCore::OAuthUser", "id": user["sub"]}
    tags = {"iss": namespace["ISSUER"], "aud": namespace["CLIENT_ID"], "token_use": "id"}
    tags.update(changes)
    result = cedarpy.is_authorized({
        "principal": principal,
        "action": {"type": "AgentCore::Action", "id": namespace["TOOL_NAME"]},
        "resource": {"type": "AgentCore::Gateway", "id": namespace["gateway_entry"]["arn"]},
        "context": {"input": {"customer_id": customer}},
    }, namespace["CEDAR"], [{
        "uid": principal, "attrs": {}, "parents": [],
        "tags": {key: value for key, value in tags.items() if value is not None},
    }])
    assert not result.diagnostics.errors, result.diagnostics.errors
    assert result.allowed == want


@pytest.mark.parametrize("drift", ["engine", "iam", "policy"])
def test_changed_configuration_is_not_overwritten(policy_workspace, drift):
    aws = policy_workspace
    namespace = policy_setup(aws)
    if drift == "engine":
        aws.objects["gateway"]["policyEngineConfiguration"]["mode"] = "LOG_ONLY"
    elif drift == "iam":
        aws.objects["role_policies"][namespace["role_entry"]["name"], namespace["POLICY_IAM_NAME"]]["Statement"][0]["Resource"] = "*"
    else:
        aws.objects["policy"]["definition"]["cedar"]["statement"] = "permit(principal, action, resource);"
    count = len(aws.calls)
    with pytest.raises(AssertionError):
        policy_setup(aws)
    assert not [method for _, method, _ in aws.calls[count:] if method.startswith(("create_", "update_", "put_"))]


def test_cleanup_checks_every_policy_and_definition_before_delete(policy_workspace):
    aws = policy_workspace
    namespace = policy_setup(aws)
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    exec(check, namespace)
    aws.objects["policy"]["definition"]["cedar"]["statement"] = "permit(principal, action, resource);"
    count = len(aws.calls)
    with pytest.raises(AssertionError, match="POLICY_DEFINITION_CHANGED"):
        exec(check, namespace)
    assert not any(method.startswith("delete_") for _, method, _ in aws.calls[count:])


def test_cleanup_removes_policy_before_engine(policy_workspace):
    aws = policy_workspace
    namespace = policy_setup(aws)
    state = namespace["state"]
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    exec(check, namespace)
    delete = next(
        c.source for c in build_cleanup().cells
        if c.cell_type == "code" and "control.delete_policy_engine(" in c.source
    )
    with pytest.raises(AssertionError, match="GATEWAY_STILL_EXISTS"):
        exec(delete, namespace)
    state.forget("gateway.instance", expected=state.get("gateway.instance"))
    del aws.objects["gateway"]
    exec(delete, namespace)
    assert state.get("policy.customer") is None and state.get("policy.engine") is None
    methods = [method for _, method, _ in aws.calls]
    assert methods.index("delete_policy") < methods.index("delete_policy_engine")


@pytest.mark.parametrize("denial", [
    {"error": {"code": -32003, "message": "Tool call denied by policy"}},
    {"result": {"isError": True, "content": [{"type": "text", "text": "Tool call denied by policy"}]}},
])
def test_wire_contract_accepts_gateway_policy_denial_shapes(denial):
    execute_wire_test(denial)


@pytest.mark.parametrize("denial", [
    {"error": {"code": -32002, "message": "insufficient_scope"}},
    {"error": {"code": -32000, "message": "upstream timeout"}},
    {"result": {"isError": False, "content": [{"type": "text", "text": "policy denied"}]}},
])
def test_wire_contract_does_not_misreport_other_errors_as_policy_denials(denial):
    with pytest.raises(AssertionError):
        execute_wire_test(denial)


def execute_wire_test(denial):
    code = next(c.source for c in build_policy().cells if c.cell_type == "code" and "def mcp_message" in c.source)

    class WireClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, *, json, **kwargs):
            if json["method"] == "initialize":
                message = {"result": {"protocolVersion": "2025-03-26"}}
            elif json["params"]["arguments"]["customer_id"] == "cliente-001" and wire_counts[0] == 0:
                wire_counts[0] += 1
                message = {"result": {"structuredContent": {
                    "execution": "AWS_LAMBDA", "synthetic": True,
                    "customer_id": "cliente-001", "risk": "low", "lambda_request_id": "lambda-real-test",
                }}}
            else:
                message = deepcopy(denial)
            return httpx.Response(
                200, request=httpx.Request("POST", url),
                json={"jsonrpc": "2.0", "id": json["id"], **message},
                headers={"x-amzn-requestid": "aws-wire-test"},
            )

    wire_counts = [0]
    with patch("httpx.Client", WireClient):
        exec(code, {
            "httpx": httpx, "json": json,
            "tokens": {"analista": "memory-only", "auditor": "memory-only"},
            "GATEWAY_URL": "https://example.invalid/mcp", "TOOL_NAME": "customer___customer_risk",
        })


def test_recorded_policy_hash_matches_definition(policy_workspace):
    namespace = policy_setup(policy_workspace)
    assert namespace["policy_entry"]["statement_sha256"] == hashlib.sha256(namespace["CEDAR"].encode()).hexdigest()
