import getpass
import json
import os
import warnings
from unittest.mock import Mock, patch

import nbformat
import pytest

from scripts.run_sdk_notebooks import execute, redact, selection, session_credentials

ACCOUNT = "123456789012"


@pytest.fixture
def notebooks(tmp_path):
    directory = tmp_path / "notebooks"
    directory.mkdir()
    for lab in ("00", "01", "99"):
        nb = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell("Consultar a AWS."),
            nbformat.v4.new_code_cell("assert True"),
        ], metadata={"workshop": {"execution": "AWS", "provisioning": "NOTEBOOK_SDK"}})
        nbformat.write(nb, directory / (lab + "_test.ipynb"))
    return tmp_path


def identity(account=ACCOUNT):
    return {
        "Account": account, "Arn": f"arn:aws:iam::{account}:role/Session",
        "ResponseMetadata": {"RequestId": "sts-fixture"},
    }


def test_other_account_never_starts_a_kernel(notebooks):
    paths = selection(notebooks, ["00", "01"])
    aws = Mock()
    aws.client.return_value.get_caller_identity.return_value = identity("999999999999")
    with patch("scripts.run_sdk_notebooks.boto3.Session", return_value=aws), patch(
        "scripts.run_sdk_notebooks.NotebookClient",
    ) as kernel:
        with pytest.raises(ValueError, match="ACCOUNT_MISMATCH"):
            execute(notebooks, paths, account=ACCOUNT, region="us-west-2", output=notebooks / "out")
    kernel.assert_not_called()
    rows = json.loads((notebooks / "out/report.json").read_text())
    assert [row["status"] for row in rows] == ["BLOCKED", "BLOCKED"]


@pytest.mark.parametrize("labs", [["01", "00"], ["00", "00"], ["99", "01"]])
def test_selection_requires_order_and_explicit_cleanup_last(notebooks, labs):
    with pytest.raises(ValueError, match="UNIQUE_ORDER"):
        selection(notebooks, labs)


def test_unconverted_notebook_rejected_before_execution(notebooks):
    path = notebooks / "notebooks/01_test.ipynb"
    nb = nbformat.read(path, as_version=4)
    nb.metadata.workshop.pop("provisioning")
    nbformat.write(nb, path)
    with pytest.raises(ValueError, match="MIGRATION_REQUIRED"):
        selection(notebooks, ["00", "01"])


def test_static_validation_never_queries_aws_or_claims_operational_acceptance(notebooks):
    with patch("scripts.run_sdk_notebooks.boto3.Session") as aws, patch(
        "scripts.run_sdk_notebooks.NotebookClient",
    ) as kernel:
        rows = execute(
            notebooks, selection(notebooks, ["00"]), account="", region="us-west-2",
            output=notebooks / "out", validate_only=True,
        )
    aws.assert_not_called()
    kernel.assert_not_called()
    assert rows[0]["status"] == "VALID" and rows[0]["validation"] == "STATIC_ONLY"


def test_failed_notebook_stops_following_notebooks_and_saves_sanitized_evidence(notebooks, monkeypatch):
    aws = Mock()
    aws.client.return_value.get_caller_identity.return_value = identity()
    monkeypatch.setenv("AWS_SESSION_TOKEN", "temporary-session-only")
    seen = []

    class FailedKernel:
        def __init__(self, notebook, **kwargs):
            self.notebook = notebook
            seen.append(kwargs)

        def execute(self, **kwargs):
            assert kwargs["env"]["WORKSHOP_EXPECTED_ACCOUNT"] == ACCOUNT
            cell = self.notebook.cells[1]
            cell.execution_count = 1
            cell.outputs = [nbformat.v4.new_output(
                "error", ename="ClientError", evalue="temporary-session-only", traceback=[],
            )]
            raise ValueError("execution failed")

    with patch("scripts.run_sdk_notebooks.boto3.Session", return_value=aws), patch(
        "scripts.run_sdk_notebooks.NotebookClient", FailedKernel,
    ):
        rows = execute(
            notebooks, selection(notebooks, ["00", "01"]), account=ACCOUNT, region="us-west-2",
            output=notebooks / "out",
        )
    assert len(seen) == 1 and rows[0]["status"] == "FAIL"
    assert not (notebooks / "out/01_test.ipynb").exists()
    for path in (notebooks / "out").iterdir():
        assert "temporary-session-only" not in path.read_text()


def test_credentials_and_jwt_are_removed_from_outputs():
    jwt = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl"
    result = redact(
        {"text": "synthetic-session " + jwt},
        {"AWS_SESSION_TOKEN": "synthetic-session"},
    )
    assert result == {"text": "[REDACTED] [REDACTED]"}


def test_hidden_credentials_are_scoped_to_the_process_and_restored(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "original-profile")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "original-access")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    temporary = ["ASIA" + "A" * 16, "s" * 40, "synthetic-session"]
    with patch("getpass.getpass", side_effect=temporary), pytest.raises(RuntimeError, match="test failure"):
        with session_credentials(True):
            assert os.environ["AWS_SESSION_TOKEN"] == temporary[2]
            assert "AWS_PROFILE" not in os.environ
            raise RuntimeError("test failure")
    assert os.environ["AWS_PROFILE"] == "original-profile"
    assert os.environ["AWS_ACCESS_KEY_ID"] == "original-access"
    assert "AWS_SECRET_ACCESS_KEY" not in os.environ and "AWS_SESSION_TOKEN" not in os.environ


def test_credential_prompt_refuses_a_terminal_that_would_echo(monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "original-profile")

    def cannot_hide(_prompt):
        warnings.warn("Input may be echoed", getpass.GetPassWarning, stacklevel=2)
        raise AssertionError("Fallback input must not be reached")

    with patch("getpass.getpass", side_effect=cannot_hide), pytest.raises(getpass.GetPassWarning):
        with session_credentials(True):
            raise AssertionError("Execution must not start")
    assert os.environ["AWS_PROFILE"] == "original-profile"


def test_invalid_credentials_do_not_modify_the_environment(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "original")
    with patch("getpass.getpass", side_effect=["invalid", "s" * 40, "synthetic"]), pytest.raises(
        ValueError, match="AWS_TEMPORARY_SESSION_CREDENTIALS_REQUIRED",
    ):
        with session_credentials(True):
            raise AssertionError("Execution must not start")
    assert os.environ["AWS_ACCESS_KEY_ID"] == "original"
