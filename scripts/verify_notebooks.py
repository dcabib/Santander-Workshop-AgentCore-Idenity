"""Valida o material e executa as aulas contra serviços AWS, sem fallback."""

import argparse
import ast
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from nbclient import NotebookClient

from santander_demo.aws_workshop.config import load
from santander_demo.aws_workshop.manifest import LABS, account_plan, check_selection, selected_labs

ROOT = Path(__file__).resolve().parents[1]


def validate_notebook(notebook):
    if notebook.metadata.get("workshop", {}).get("execution") != "AWS":
        raise ValueError("AWS_NOTEBOOK_REQUIRED")
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
            if isinstance(node, ast.ImportFrom) and node.module in {
                "santander_demo.local", "santander_demo.rag.local",
            }:
                raise ValueError("SIMULATION_IMPORT_FORBIDDEN")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true",
                        help="Validar sintaxe/material; não conta como aceite operacional")
    parser.add_argument("--labs", nargs="+", choices=LABS,
                        help="Selecione as aulas preparadas; omitir usa a seleção padrão da topologia")
    parser.add_argument("--output", default="evidence/notebooks-aws.json")
    args = parser.parse_args()
    if not args.validate_only and not (
        os.environ.get("CODEBUILD_BUILD_ARN")
        or os.environ.get("AWS_EXECUTION_ENV", "").startswith("CloudShell")
        or Path("/opt/ml/metadata/resource-metadata.json").exists()
    ):
        parser.error("Execute os notebooks no runner AWS do projeto ou no ambiente SageMaker/CloudShell.")
    out = ROOT / "evidence/executed"
    out.mkdir(parents=True, exist_ok=True)
    results = []
    paths = [
        p for p in sorted((ROOT / "notebooks").glob("*.ipynb"))
        if not args.labs or p.name[:2] in args.labs
    ]
    if not paths:
        parser.error("Nenhuma aula selecionada")
    if not args.validate_only:
        try:
            config = load(os.environ.get("WORKSHOP_CONFIG", ROOT / "config/aws.workshop.json"))
            selected = selected_labs(config, args.labs)
            paths = [path for path in paths if path.name[:2] in selected]
            if {path.name[:2] for path in paths} != set(selected):
                raise ValueError("SELECTED_NOTEBOOK_FILES_MISSING")
            readiness = ROOT / "evidence/workshop-prerequisites.json"
            readiness.write_text(json.dumps(account_plan(config, selected), indent=2) + "\n")
            # Conferir a seleção inteira antes de iniciar o primeiro kernel.
            check_selection(config, selected)
        except Exception as exc:
            # Uma tentativa bloqueada não pode deixar um PASS anterior como seu resultado.
            target = Path(args.output)
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_text(json.dumps([{
                "notebook": path.name, "status": "BLOCKED", "validation": "AWS_PREFLIGHT",
                "started_at": datetime.now(UTC).isoformat(),
                "error_type": type(exc).__name__, "error_message": str(exc)[:2000],
            } for path in paths], indent=2) + "\n")
            raise
    for path in paths:
        notebook = nbformat.read(path, as_version=4)
        start = time.monotonic()
        result = {
            "notebook": path.name, "status": "FAIL",
            "validation": "STATIC_ONLY" if args.validate_only else "AWS_EXECUTION",
            "started_at": datetime.now(UTC).isoformat(),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "code_cells": sum(cell.cell_type == "code" for cell in notebook.cells),
        }
        try:
            validate_notebook(notebook)
            if not args.validate_only:
                NotebookClient(
                    notebook, timeout=300, resources={"metadata": {"path": str(ROOT)}},
                ).execute(env=dict(os.environ))
                if any(cell.execution_count is None for cell in notebook.cells if cell.cell_type == "code"):
                    raise ValueError("INCOMPLETE_NOTEBOOK_EXECUTION")
            result["status"] = "VALID" if args.validate_only else "PASS"
        except Exception as exc:
            result["error_type"] = type(exc).__name__
            result["error_message"] = str(exc)[:2000]
        finally:
            result["elapsed_seconds"] = round(time.monotonic() - start, 2)
            if not args.validate_only:
                nbformat.write(notebook, out / path.name)
            results.append(result)
            target = Path(args.output)
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_text(json.dumps(results, indent=2) + "\n")
        print(f"{path.name}: {result['status']} ({result['validation']})", flush=True)
        if result["status"] == "FAIL":
            raise SystemExit("Aula interrompida; veja " + args.output)


if __name__ == "__main__":
    main()
