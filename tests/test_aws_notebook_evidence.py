import hashlib

import nbformat
import pytest

from scripts.audit_notebooks import audit


@pytest.fixture
def evidence(tmp_path):
    source, executed = tmp_path / "source", tmp_path / "executed"
    source.mkdir()
    executed.mkdir()
    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell("Consultar AWS."),
        nbformat.v4.new_code_cell("assert True"),
    ])
    path = source / "00_preflight.ipynb"
    nbformat.write(notebook, path)
    row = {"notebook": path.name, "status": "PASS", "validation": "AWS_EXECUTION",
           "code_cells": 1, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    notebook.cells[1].execution_count = 1
    nbformat.write(notebook, executed / path.name)
    return [row], source, executed


@pytest.mark.parametrize("fault", ["missing", "static", "stale", "partial", "different", "error"])
def test_evidence_never_promotes_incomplete_or_changed_execution(evidence, fault):
    rows, source, executed = evidence
    path = executed / rows[0]["notebook"]
    notebook = nbformat.read(path, as_version=4)
    if fault == "missing":
        rows.clear()
    elif fault == "static":
        rows[0]["validation"] = "STATIC_ONLY"
    elif fault == "stale":
        rows[0]["source_sha256"] = "wrong"
    elif fault == "partial":
        notebook.cells[1].execution_count = None
    elif fault == "different":
        notebook.cells[1].source = "pass"
    elif fault == "error":
        notebook.cells[1].outputs = [nbformat.v4.new_output(
            "error", ename="AssertionError", evalue="failed", traceback=[],
        )]
    nbformat.write(notebook, path)
    with pytest.raises(ValueError):
        audit(rows, source, executed)


def test_complete_matching_execution_is_accepted(evidence):
    assert audit(*evidence)["status"] == "MATCH"


def test_selected_acceptance_cannot_omit_a_missing_notebook_file(evidence):
    with pytest.raises(ValueError, match="SELECTED_NOTEBOOK_FILES_MISSING"):
        audit(*evidence, labs=["00", "09"])


def test_selected_acceptance_reports_only_executed_scope(evidence):
    result = audit(*evidence, labs=["00"])
    assert result["labs"] == ["00"]
    assert result["notebooks"] == 1
