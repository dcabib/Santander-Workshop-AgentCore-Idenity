import ast
from unittest.mock import Mock, patch

import pytest

from scripts.sdk_notebook_lessons import build_preflight


def test_preflight_starts_with_an_empty_checkout_and_only_queries_identity(tmp_path, monkeypatch):
    """O primeiro notebook deve funcionar sem os outputs de qualquer implantação."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test-workshop'\n")
    monkeypatch.chdir(tmp_path)
    aws = Mock()
    aws.region_name = "us-west-2"
    sts = Mock()
    sts.get_caller_identity.return_value = {
        "Account": "123456789012",
        "Arn": "arn:aws:sts::123456789012:assumed-role/AuthorizedRole/session",
        "ResponseMetadata": {"RequestId": "sts-request-id"},
    }
    control = Mock()
    control.meta.service_model.operation_names = [
        "CreateGateway", "CreateGatewayTarget", "CreateAgentRuntime",
        "CreateMemory", "CreatePolicyEngine", "CreatePolicy",
    ]

    def client(service):
        return {"sts": sts, "bedrock-agentcore-control": control}[service]

    aws.client.side_effect = client
    namespace = {}
    with patch("boto3.Session", return_value=aws):
        for cell in build_preflight().cells:
            if cell.cell_type == "code":
                exec(compile(cell.source, "00_preflight", "exec"), namespace)
    assert sts.method_calls == [("get_caller_identity", (), {})]
    assert control.method_calls == []
    assert not (tmp_path / "config").exists()
    assert namespace["state"].data["resources"] == {}
    assert namespace["ACCOUNT_ID"] == "123456789012"


def test_preflight_contains_no_cloudformation_or_deploy_execution():
    notebook = build_preflight()
    assert notebook.metadata.workshop.provisioning == "NOTEBOOK_SDK"
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        ast.parse(cell.source)
        assert "stack_outputs" not in cell.source
        assert "cloudformation" not in cell.source.lower()
        assert "AWSWorkshop(" not in cell.source
        assert "subprocess" not in cell.source
        assert "aws.workshop.json" not in cell.source


def test_expected_account_guard_precedes_any_resource_state(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test-workshop'\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKSHOP_EXPECTED_ACCOUNT", "111111111111")
    aws = Mock()
    aws.region_name = "us-west-2"
    aws.client.return_value.get_caller_identity.return_value = {
        "Account": "999999999999", "Arn": "arn:aws:iam::999999999999:role/Session",
        "ResponseMetadata": {"RequestId": "other-account"},
    }
    namespace = {}
    with patch("boto3.Session", return_value=aws), pytest.raises(RuntimeError, match="ACCOUNT_MISMATCH"):
        for cell in build_preflight().cells:
            if cell.cell_type == "code":
                exec(cell.source, namespace)
    assert not (tmp_path / ".workshop").exists()
    aws.client.assert_called_once_with("sts")
