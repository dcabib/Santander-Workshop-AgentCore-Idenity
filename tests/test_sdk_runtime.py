"""Contratos de Runtime, integridade de artefatos e identidade do workload."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from botocore.exceptions import ClientError

from scripts.sdk_notebook_lessons import build_cleanup, build_runtime
from scripts.sdk_runtime_lesson import SERVER_SOURCE
from tests.test_sdk_gateway import ACCOUNT, REGION, AWSContract


class RuntimeAWS(AWSContract):
    def __init__(self):
        super().__init__()
        self.objects["s3"] = {}

    def respond(self, service, method, args):
        objects = self.objects
        if method == "create_bucket":
            objects["bucket"] = args["Bucket"]
            return {}
        if method == "head_bucket":
            if "bucket" not in objects:
                raise ClientError({"Error": {"Code": "404", "Message": "Not found"}}, "HeadBucket")
            assert args["Bucket"] == objects["bucket"]
            return {"BucketRegion": REGION}
        if method in {"put_public_access_block", "put_bucket_encryption"}:
            return {}
        if method == "put_object":
            assert args["ExpectedBucketOwner"] == ACCOUNT and args["IfNoneMatch"] == "*"
            assert args["Key"] not in objects["s3"]
            objects["s3"][args["Key"]] = args["Body"]
            return {}
        if method in {"get_object", "head_object"}:
            if args["Key"] not in objects["s3"]:
                raise ClientError({"Error": {"Code": "404", "Message": "Not found"}}, "GetObject")
            return {"Body": io.BytesIO(objects["s3"][args["Key"]]), "ServerSideEncryption": "AES256"}
        if method == "list_objects_v2":
            return {"Contents": [{"Key": key} for key in objects["s3"]]}
        if method == "delete_object":
            del objects["s3"][args["Key"]]
            return {}
        if method == "delete_bucket":
            assert not objects["s3"]
            del objects["bucket"]
            return {}
        if method == "create_agent_runtime":
            runtime_id = args["agentRuntimeName"] + "-abcdefghij"
            objects["runtime"] = {
                **args, "agentRuntimeId": runtime_id,
                "agentRuntimeArn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/{runtime_id}",
                "status": "READY",
            }
            objects["runtime_logs"] = "/aws/bedrock-agentcore/runtimes/" + runtime_id + "-DEFAULT"
            return objects["runtime"]
        if method == "get_agent_runtime":
            if "runtime" not in objects:
                raise self.clients["bedrock-agentcore-control"].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return objects["runtime"]
        if method == "delete_agent_runtime":
            del objects["runtime"]
            return {}
        if method == "list_tags_for_resource":
            return {"tags": objects["runtime"]["tags"]}
        if method == "invoke_agent_runtime":
            request = json.loads(args["payload"])
            runtime = objects["runtime"]
            if request["method"] == "initialize":
                result = {"protocolVersion": "2025-03-26", "capabilities": {}}
            elif request["method"] == "tools/list":
                result = {"tools": [{"name": "workload_identity"}]}
            else:
                result = {"isError": False, "structuredContent": {
                    "execution": "AWS_AGENTCORE_RUNTIME", "account": ACCOUNT,
                    "principal": f"arn:aws:sts::{ACCOUNT}:assumed-role/{runtime['environmentVariables']['WORKSHOP_ROLE_NAME']}/runtime-session",
                    "run_id": runtime["environmentVariables"]["WORKSHOP_RUN"],
                    "sts_request_id": "sts-runtime-request",
                }}
            message = json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result})
            return {
                "response": io.BytesIO(("event: message\ndata: " + message + "\n\n").encode()),
                "contentType": "text/event-stream",
                "ResponseMetadata": {"RequestId": "runtime-native-request"},
            }
        if method == "stop_runtime_session":
            return {"ResponseMetadata": {"RequestId": "stop-session"}}
        if method == "describe_log_groups":
            return {"logGroups": [{"logGroupName": objects["runtime_logs"]}]} if "runtime_logs" in objects else {"logGroups": []}
        if method == "delete_log_group":
            assert args["logGroupName"] == objects["runtime_logs"]
            del objects["runtime_logs"]
            return {}
        if method == "list_attached_role_policies":
            return {"AttachedPolicies": []}
        if method == "list_role_policies":
            return {"PolicyNames": [name for (role, name) in objects["role_policies"] if role == args["RoleName"]]}
        if method == "delete_role_policy":
            del objects["role_policies"][args["RoleName"], args["PolicyName"]]
            return {}
        if method == "delete_role":
            assert "runtime" not in objects
            del objects["roles"][args["RoleName"]]
            return {}
        if method == "get_role" and args["RoleName"] not in objects["roles"]:
            raise self.clients["iam"].exceptions.NoSuchEntityException(
                {"Error": {"Code": "NoSuchEntity", "Message": "Not found"}}, method,
            )
        return super().respond(service, method, args)


def run_package_command(args, **kwargs):
    if args[:2] == ["uv", "export"]:
        Path(args[args.index("--output-file") + 1]).write_text("mcp==1.28.1\n")
    else:
        assert "--require-hashes" in args and "--only-binary" in args
        assert args[args.index("--python-platform") + 1] == "aarch64-manylinux2014"
        package = Path(args[args.index("--target") + 1])
        (package / "dependency.py").write_text("# package fixture\n")
    return SimpleNamespace(returncode=0)


def execute_runtime(aws, *, bucket_status=403):
    denied_runtime = httpx.Response(403, headers={"x-amzn-requestid": "runtime-denial"})
    denied_bucket = httpx.Response(bucket_status, headers={"x-amz-request-id": "s3-denial"})
    namespace = {}
    with (
        patch("boto3.Session", return_value=aws),
        patch("httpx.post", return_value=denied_runtime),
        patch("httpx.get", return_value=denied_bucket),
        patch("subprocess.run", side_effect=run_package_command),
        patch("time.sleep"),
    ):
        for cell in build_runtime().cells:
            if cell.cell_type == "code":
                exec(cell.source, namespace)
    return namespace


@pytest.fixture
def runtime_workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='runtime-test'\n")
    (tmp_path / "uv.lock").write_text("# locked test dependencies\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_runtime_sdk_contract_resume_and_cleanup(runtime_workspace):
    aws = RuntimeAWS()
    first = execute_runtime(aws)
    initial_count = len(aws.calls)
    namespace = execute_runtime(aws)
    assert not [
        method for _, method, _ in aws.calls[initial_count:]
        if method.startswith(("create_", "put_")) and method != "put_retention_policy"
    ]
    assert first["runtime_entry"] == namespace["runtime_entry"]
    create = next(args for _, method, args in aws.calls if method == "create_agent_runtime")
    assert "authorizerConfiguration" not in create
    assert create["agentRuntimeArtifact"]["codeConfiguration"]["runtime"] == "PYTHON_3_12"
    assert create["protocolConfiguration"] == {"serverProtocol": "MCP"}
    for cell in build_cleanup().cells:
        if cell.cell_type == "code" and "supported =" in cell.source:
            exec(cell.source, namespace)
    # Simula a paginação de DescribeLogGroups sem executar chamadas fora do contrato SDK.
    log_client = namespace["logs"]
    log_client.get_paginator = lambda name: SimpleNamespace(
        paginate=lambda **args: [log_client.describe_log_groups(**args)],
    )
    cells = [cell for cell in build_cleanup().cells if cell.cell_type == "code"]
    start = next(index for index, cell in enumerate(cells) if "control.delete_agent_runtime(" in cell.source)
    for cell in cells[start:]:
        exec(cell.source, namespace)
    assert not namespace["state"].data["resources"]
    assert "bucket" not in aws.objects and "runtime" not in aws.objects
    deletes = [method for _, method, _ in aws.calls if method.startswith("delete_")]
    assert deletes.index("delete_agent_runtime") < deletes.index("delete_object") < deletes.index("delete_bucket")


def test_public_bucket_fails_before_uploading_runtime_code(runtime_workspace):
    aws = RuntimeAWS()
    with pytest.raises(AssertionError, match="EXPECTED_PRIVATE_ARTIFACT_BUCKET"):
        execute_runtime(aws, bucket_status=200)
    assert list(aws.objects["s3"]) == ["workshop-owner.json"]
    assert not any(method == "create_agent_runtime" for _, method, _ in aws.calls)


def test_artifact_and_cleanup_refuse_unregistered_changes(runtime_workspace):
    aws = RuntimeAWS()
    namespace = execute_runtime(aws)
    (runtime_workspace / "uv.lock").write_text("# changed dependencies\n")
    call_count = len(aws.calls)
    with pytest.raises(AssertionError, match="RUNTIME_LOCK_CHANGED"):
        execute_runtime(aws)
    assert not any(method.startswith(("create_", "put_", "delete_")) for _, method, _ in aws.calls[call_count:])
    aws.objects["s3"]["another-object"] = b"not owned by this notebook"
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    call_count = len(aws.calls)
    with pytest.raises(AssertionError, match="UNREGISTERED_RUNTIME_BUCKET_OBJECTS"):
        exec(check, namespace)
    assert not any(method.startswith("delete_") for _, method, _ in aws.calls[call_count:])


@pytest.mark.parametrize("error_code,allowed", [
    ("ResourceNotFoundException", True),
    ("AccessDeniedException", False),
])
def test_runtime_session_cleanup_accepts_only_already_absent(runtime_workspace, error_code, allowed):
    aws = RuntimeAWS()
    original = aws.respond

    def response(service, method, args):
        if method == "stop_runtime_session":
            exception = getattr(aws.clients["bedrock-agentcore"].exceptions, error_code)
            raise exception({
                "Error": {"Code": error_code, "Message": "Session check"},
                "ResponseMetadata": {"RequestId": "stop-session-response"},
            }, "StopRuntimeSession")
        return original(service, method, args)

    aws.respond = response
    if allowed:
        namespace = execute_runtime(aws)
        assert namespace["state"].get("runtime.logs")
    else:
        with pytest.raises(ClientError):
            execute_runtime(aws)


def test_runtime_tool_uses_workload_sts_identity_and_rejects_another_role(monkeypatch):
    for key, value in {
        "WORKSHOP_ACCOUNT": ACCOUNT, "WORKSHOP_ROLE_NAME": "expected-role", "WORKSHOP_RUN": "test-run",
    }.items():
        monkeypatch.setenv(key, value)
    namespace = {"__name__": "runtime_test"}
    exec(SERVER_SOURCE, namespace)
    identity = {
        "Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/expected-role/session",
        "ResponseMetadata": {"RequestId": "sts-native"},
    }
    with patch("boto3.client", return_value=SimpleNamespace(get_caller_identity=lambda: identity)):
        result = namespace["workload_identity"]()
        assert result["principal"] == identity["Arn"] and result["sts_request_id"] == "sts-native"
        identity["Arn"] = f"arn:aws:sts::{ACCOUNT}:assumed-role/another-role/session"
        with pytest.raises(AssertionError):
            namespace["workload_identity"]()
