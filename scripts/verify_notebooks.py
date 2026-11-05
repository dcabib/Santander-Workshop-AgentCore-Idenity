"""Verificação estática das aulas SDK e dos cadernos de referência. Não chama AWS."""

import argparse
import ast
import json
from pathlib import Path

import nbformat

from santander_demo.notebook_catalog import lab_id

ROOT = Path(__file__).resolve().parents[1]


def validate_notebook(notebook):
    nbformat.validate(notebook)
    workshop = notebook.metadata.get("workshop", {})
    if workshop.get("execution") == "REFERENCE_ONLY":
        if any(cell.cell_type == "code" for cell in notebook.cells):
            raise ValueError("REFERENCE_MUST_NOT_EXECUTE")
        return "REFERENCE_ONLY"
    if workshop.get("execution") != "AWS" or workshop.get("provisioning") != "NOTEBOOK_SDK":
        raise ValueError("SDK_NOTEBOOK_REQUIRED")
    forbidden = {"WORKSHOP_MODE", "RUN_AWS", "LocalLifecycle", "LocalCognitoRagLab", "Workshop"}
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        if index == 0 or notebook.cells[index - 1].cell_type != "markdown":
            raise ValueError(f"Célula {index + 1} precisa explicar seu código")
        tree = ast.parse(cell.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in forbidden:
                raise ValueError("EXECUTION_FALLBACK_FORBIDDEN:" + node.id)
        compile(cell.source, "notebook", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    return "NOTEBOOK_SDK"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true", help="Compatibilidade: esta ferramenta sempre faz validação estática.")
    parser.add_argument("--labs", nargs="+", help="Números publicados, por exemplo 00 01 15 16 90.")
    args = parser.parse_args()
    labs = {lab_id(lab) for lab in args.labs} if args.labs else None
    paths = [p for p in sorted((ROOT / "notebooks").glob("*.ipynb")) if not labs or lab_id(p) in labs]
    if not paths or (labs and {lab_id(path) for path in paths} != labs):
        parser.error("Aula não encontrada")
    rows = [{"notebook": path.name, "type": validate_notebook(nbformat.read(path, as_version=4)),
             "status": "VALID", "validation": "STATIC_ONLY"} for path in paths]
    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
