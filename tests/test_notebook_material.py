"""Contratos da publicação após retirar o deploy legado."""
from pathlib import Path

import nbformat
import pytest

from santander_demo.notebook_catalog import LESSON_TITLES, REFERENCE_LABS, published_stem
from scripts.generate_aws_notebooks import build_notebook
from scripts.run_sdk_notebooks import selection
from scripts.verify_notebooks import validate_notebook

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", sorted(LESSON_TITLES, key=published_stem))
def test_all_published_notebooks_build_without_legacy_infrastructure(name):
    notebook = build_notebook(name)
    expected = "REFERENCE_ONLY" if name[:2] in REFERENCE_LABS else "NOTEBOOK_SDK"
    assert validate_notebook(notebook) == expected
    assert any(cell.get("attachments") for cell in notebook.cells)


@pytest.mark.parametrize("lab", ["13", "14", "90", "91", "92"])
def test_sdk_executor_rejects_architecture_references(lab):
    with pytest.raises(ValueError, match="SDK_MIGRATION_REQUIRED"):
        selection(ROOT, [lab])


def test_static_validator_rejects_code_in_reference():
    notebook = build_notebook("90_multiconta_santander")
    notebook.cells.append(nbformat.v4.new_code_cell("print('unexpected executable cell')"))
    with pytest.raises(ValueError, match="REFERENCE_MUST_NOT_EXECUTE"):
        validate_notebook(notebook)


def test_static_validator_rejects_old_predeploy_mode():
    notebook = nbformat.v4.new_notebook(metadata={"workshop": {"execution": "AWS"}})
    with pytest.raises(ValueError, match="SDK_NOTEBOOK_REQUIRED"):
        validate_notebook(notebook)
