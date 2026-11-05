"""Contratos do fluxo Registry e rejeição de descritores alterados."""

import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from scripts.sdk_notebook_lessons import build_cleanup, build_registry_execution
from tests.test_sdk_gateway import ACCOUNT, REGION
from tests.test_sdk_registry import run_registry
from tests.test_sdk_registry_personas import PersonaAWS, run_personas


class RecordAWS(PersonaAWS):
    def __init__(self):
        super().__init__()
        self.active_persona = None
        self.persona_calls = []
        self.bad_discovery = False
        self.bad_denial = False

    def persona_session(self, name):
        owner = self

        def client(service):
            base = owner.client(service)

            class Client:
                exceptions = base.exceptions

                def __getattr__(self, method):
                    def call(**args):
                        previous = owner.active_persona
                        owner.active_persona = name
                        owner.persona_calls.append((name, method))
                        try:
                            return getattr(base, method)(**args)
                        finally:
                            owner.active_persona = previous
                    return call

            return Client()

        return SimpleNamespace(client=client)

    def session(self, **args):
        if args.get("aws_access_key_id"):
            return self.persona_session(args["aws_access_key_id"])
        return self

    def deny(self, method):
        raise ClientError({
            "Error": {"Code": "ThrottlingException" if self.bad_denial else "AccessDeniedException",
                      "Message": "Test denial"},
            "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "deny-request"},
        }, method)

    def respond(self, service, method, args):
        if method == "assume_role":
            persona = {
                "admin_persona": "approver", "publisher_persona": "publisher",
                "consumer_persona": "consumer",
            }[args["RoleArn"].rsplit("/", 1)[1]]
            if "Policy" in args:
                assert persona == "consumer"
                assert all(
                    action.startswith("agent-registry:")
                    for action in json.loads(args["Policy"])["Statement"][0]["Action"]
                )
                persona = "discovery-only"
            return {
                "Credentials": {"AccessKeyId": persona, "SecretAccessKey": "test", "SessionToken": "test"},
                "AssumedRoleUser": {"Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/{persona}/test"},
                "ResponseMetadata": {"RequestId": "assume-request"},
            }
        if method == "invoke_agent_runtime":
            if self.active_persona == "discovery-only":
                self.deny(method)
            assert self.active_persona in {None, "consumer"}
            request = json.loads(args["payload"])
            result = {}
            if request["method"] == "tools/list":
                result = {"tools": [{"name": "workload_identity", "inputSchema": {"type": "object"}}]}
            if request["method"] == "tools/call":
                role = self.objects["runtime"]["roleArn"].rsplit("/", 1)[1]
                result = {"structuredContent": {
                    "execution": "AWS_AGENTCORE_RUNTIME", "account": ACCOUNT,
                    "run_id": self.run_id, "principal": f"arn:aws:sts::{ACCOUNT}:assumed-role/{role}/test",
                    "sts_request_id": "workload-sts-request",
                }}
            return {
                "response": io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}).encode()),
                "contentType": "application/json", "ResponseMetadata": {"RequestId": "runtime-request"},
            }
        if method == "stop_runtime_session":
            return {"ResponseMetadata": {"RequestId": "stop-request"}}
        if method == "create_registry_record":
            assert self.active_persona == "publisher"
            self.objects["record"] = {
                **{key: value for key, value in args.items() if key != "clientToken"},
                "registryArn": self.objects["registry"]["registryArn"],
                "recordId": "record123abc4",
                "recordArn": self.objects["registry"]["registryArn"] + "/record/record123abc4",
                "status": "DRAFT", "ResponseMetadata": {"RequestId": "record-request"},
            }
            return self.objects["record"]
        if method == "get_registry_record":
            if "record" not in self.objects:
                raise self.clients[service].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return self.objects["record"]
        if method == "submit_registry_record_for_approval":
            assert self.active_persona == "publisher"
            self.objects["record"]["status"] = "PENDING_APPROVAL"
            return self.objects["record"]
        if method == "update_registry_record_status":
            if self.active_persona == "publisher":
                self.deny(method)
            assert self.active_persona == "approver"
            self.objects["record"]["status"] = args["status"]
            return self.objects["record"]
        if method in {"list_registry_records", "list_discoverable_registry_records"}:
            record = self.objects.get("record")
            records = [record] if record and (method == "list_registry_records" or record["status"] == "APPROVED") else []
            return {"registryRecords": records, "ResponseMetadata": {"RequestId": "list-request"}}
        if method == "batch_get_discoverable_registry_record":
            record = dict(self.objects["record"])
            if self.bad_discovery:
                record["descriptors"] = {"mcpServer": {"data": '{"remotes":[{"url":"https://unexpected.invalid"}]}'}}
            return {"registryRecords": [record], "errors": [], "ResponseMetadata": {"RequestId": "batch-request"}}
        if method == "delete_registry_record":
            del self.objects["record"]
            return {}
        return super().respond(service, method, args)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='record-test'\n")
    monkeypatch.chdir(tmp_path)
    aws = RecordAWS()
    namespace = run_registry(aws)
    state = namespace["state"]
    aws.run_id = state.data["run_id"]
    arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/test-abcdefghij"
    role_arn = f"arn:aws:iam::{ACCOUNT}:role/{state.prefix}-runtime"
    aws.objects["runtime"] = {
        "agentRuntimeArn": arn, "agentRuntimeId": "test-abcdefghij",
        "roleArn": role_arn, "protocolConfiguration": {"serverProtocol": "MCP"},
        "status": "READY", "tags": state.tags,
    }
    state.record("runtime.instance", {"arn": arn, "id": "test-abcdefghij", "role_arn": role_arn}, lesson="03")
    state.record("runtime.artifact", {"source_hash": "source-hash"}, lesson="03")
    run_personas(aws)
    return aws


def run_record(aws):
    namespace = {}
    with patch("boto3.Session", side_effect=aws.session), patch("time.sleep"):
        for cell in build_registry_execution().cells:
            if cell.cell_type == "code":
                exec(cell.source, namespace)
    return namespace


def test_record_lifecycle_uses_personas_and_restarts_without_republishing(workspace):
    namespace = run_record(workspace)
    assert workspace.objects["record"]["status"] == "APPROVED"
    assert namespace["record_entry"]["arn"] == workspace.objects["record"]["recordArn"]
    assert ("publisher", "update_registry_record_status") in workspace.persona_calls
    assert ("approver", "update_registry_record_status") in workspace.persona_calls
    assert ("consumer", "invoke_agent_runtime") in workspace.persona_calls
    assert ("discovery-only", "invoke_agent_runtime") in workspace.persona_calls
    count = len(workspace.calls)
    run_record(workspace)
    assert not any(method.startswith(("create_", "update_", "put_", "submit_")) for _, method, _ in workspace.calls[count:])


def test_discovery_cannot_redirect_consumer_to_unreviewed_endpoint(workspace):
    workspace.bad_discovery = True
    with pytest.raises(AssertionError, match="UNTRUSTED_DISCOVERY_DESCRIPTOR"):
        run_record(workspace)
    assert ("consumer", "invoke_agent_runtime") not in workspace.persona_calls


def test_arbitrary_403_does_not_prove_publisher_separation(workspace):
    workspace.bad_denial = True
    with pytest.raises(AssertionError):
        run_record(workspace)
    assert workspace.objects["record"]["status"] == "PENDING_APPROVAL"
    assert ("approver", "update_registry_record_status") not in workspace.persona_calls


@pytest.mark.parametrize("drift", [False, True])
def test_cleanup_verifies_record_before_removing_it(workspace, drift):
    namespace = run_record(workspace)
    state = namespace["state"]
    for key in ("runtime.instance", "runtime.artifact"):
        state.forget(key, expected=state.get(key))  # Dependências representadas somente por fixtures.
    if drift:
        workspace.objects["record"]["description"] = "Changed externally"
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    if drift:
        with pytest.raises(AssertionError, match="REGISTRY_RECORD_CHANGED"):
            exec(check, namespace)
        assert not any(method == "delete_registry_record" for _, method, _ in workspace.calls)
    else:
        exec(check, namespace)
        deletion = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "registry_control.delete_registry_record(" in c.source)
        exec(deletion, namespace)
        assert state.get("registry.record.mcp") is None
        assert "record" not in workspace.objects
