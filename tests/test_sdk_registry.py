"""Registry SDK: retomada, autenticação e limpeza diante de recursos inesperados."""

from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError

from scripts.sdk_notebook_lessons import build_cleanup, build_registry
from tests.test_sdk_gateway import ACCOUNT, REGION, AWSContract


class RegistryAWS(AWSContract):
    def __init__(self):
        super().__init__()
        session = boto3.Session(
            region_name=REGION, aws_access_key_id="model-only",
            aws_secret_access_key="model-only",
        )
        for name in ("agent-registry-control", "agent-registry"):
            self.clients[name] = session.client(name)
        self.records = []
        self.unsigned_error = "AccessDeniedException"

    def client(self, service, **kwargs):
        if kwargs.get("config"):
            def denied(**args):
                raise ClientError({
                    "Error": {"Code": self.unsigned_error, "Message": "Test authentication response"},
                    "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "unsigned-request"},
                }, "ListDiscoverableRegistryRecords")
            return SimpleNamespace(list_discoverable_registry_records=denied)
        return super().client(service)

    def respond(self, service, method, args):
        if method == "create_registry":
            self.objects["registry"] = {
                **args, "registryId": "abcdefghijkl",
                "registryArn": f"arn:aws:agent-registry:{REGION}:{ACCOUNT}:registry/abcdefghijkl",
                "status": "READY", "ResponseMetadata": {"RequestId": "registry-request"},
            }
            return {"registryArn": self.objects["registry"]["registryArn"]}
        if method == "get_registry":
            if "registry" not in self.objects:
                raise self.clients[service].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return self.objects["registry"]
        if service == "agent-registry-control" and method == "list_tags_for_resource":
            return {"tags": self.objects["registry"]["tags"]}
        if method in {"list_registry_records", "list_discoverable_registry_records"}:
            return {"registryRecords": self.records, "ResponseMetadata": {"RequestId": "discovery-request"}}
        if method == "delete_registry":
            assert not self.records
            del self.objects["registry"]
            return {"status": "DELETING"}
        return super().respond(service, method, args)


def run_registry(aws):
    namespace = {}
    with patch("boto3.Session", return_value=aws), patch("time.sleep"):
        for cell in build_registry().cells:
            if cell.cell_type == "code":
                exec(cell.source, namespace)
    return namespace


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='registry-test'\n")
    monkeypatch.chdir(tmp_path)
    return RegistryAWS()


def test_registry_uses_returned_arn_and_resumes_without_creating_again(workspace):
    first = run_registry(workspace)
    count = len(workspace.calls)
    second = run_registry(workspace)
    assert first["registry_entry"] == second["registry_entry"]
    assert second["registry_entry"]["arn"] == workspace.objects["registry"]["registryArn"]
    assert not any(method.startswith(("create_", "update_", "put_")) for _, method, _ in workspace.calls[count:])
    assert workspace.objects["registry"]["approvalConfiguration"] == {"autoApprovalRules": []}


@pytest.mark.parametrize("field,value", [
    ("tags", {}),
    ("discoveryConfiguration", {"authorizerType": "CUSTOM_JWT"}),
    ("approvalConfiguration", {"autoApprovalRules": ["APPROVE_ALL"]}),
    ("autoDetection", {"status": "ACTIVE"}),
])
def test_registry_drift_stops_without_overwriting(workspace, field, value):
    run_registry(workspace)
    workspace.objects["registry"][field] = value
    count = len(workspace.calls)
    with pytest.raises(AssertionError):
        run_registry(workspace)
    assert not any(method.startswith(("create_", "update_", "put_")) for _, method, _ in workspace.calls[count:])


def test_arbitrary_403_is_not_proof_of_authentication(workspace):
    workspace.unsigned_error = "ThrottlingException"
    with pytest.raises(AssertionError, match="AUTHENTICATION_DENIAL"):
        run_registry(workspace)


def test_registry_cleanup_rejects_unknown_records_before_any_delete(workspace):
    namespace = run_registry(workspace)
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    workspace.records = [{"recordId": "unexpected"}]
    with pytest.raises(AssertionError, match="REGISTRY_RECORD_CLEANUP_REQUIRED"):
        exec(check, namespace)
    assert not any(method.startswith("delete_") for _, method, _ in workspace.calls)


def test_registry_cleanup_removes_only_registered_empty_catalog(workspace):
    namespace = run_registry(workspace)
    cells = build_cleanup().cells
    exec(next(c.source for c in cells if c.cell_type == "code" and "supported =" in c.source), namespace)
    deletion = next(c.source for c in cells if c.cell_type == "code" and "registry_control.delete_registry(" in c.source)
    exec(deletion, namespace)
    assert namespace["state"].get("registry.instance") is None
    assert namespace["state"].data["released_resources"]["registry.instance"]["id"] == "abcdefghijkl"
    assert [method for _, method, _ in workspace.calls if method.startswith("delete_")] == ["delete_registry"]
