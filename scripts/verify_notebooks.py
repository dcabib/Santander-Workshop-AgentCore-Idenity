"""Executa notebooks localmente e registra execução e cleanup por notebook."""

import ast
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def check_offline_defaults(notebook):
    """Recusa controles live/deploy/cleanup ativados antes de iniciar um kernel."""
    false_flags = {"RUN_AWS", "RUN_PIPELINE", "APPLY_CHANGESET", "RUN_AGENT", "CLEANUP_EXECUTE"}
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        if index == 0 or notebook.cells[index - 1].cell_type != "markdown":
            raise ValueError(f"Célula {index + 1} sem explicação anterior")
        for node in ast.walk(ast.parse(cell.source)):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in false_flags | {"CLEANUP_TARGET"}:
                    expected = None if target.id == "CLEANUP_TARGET" else False
                    if not isinstance(node.value, ast.Constant) or node.value.value is not expected:
                        raise ValueError(
                            f"{target.id} precisa ser {expected!r} na validação offline"
                        )


def cleanup_status(notebook, tag, field):
    cells = [cell for cell in notebook.cells if tag in cell.metadata.get("tags", [])]
    if len(cells) != 1 or cells[0].execution_count is None:
        raise ValueError(f"Esperada uma célula executada de {tag}")
    for output in cells[0].get("outputs", []):
        if output.output_type != "stream":
            continue
        for line in output.text.splitlines():
            try:
                record = ast.literal_eval(line)
            except (SyntaxError, ValueError):
                continue
            if isinstance(record, dict) and field in record:
                return record[field]
    raise ValueError(f"Resultado de {tag} não encontrado")


def main():
    environment = dict(os.environ, WORKSHOP_MODE="local", AWS_EC2_METADATA_DISABLED="true")
    environment.pop("RUN_DATABRICKS", None)
    out = ROOT / "evidence/executed"
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        started = time.monotonic()
        result = {
            "notebook": path.name,
            "status": "FAIL",
            "mode": notebook.metadata.get("santander", {}).get(
                "local_validation_mode", "LOCAL_SIMULATION"
            ),
            "started_at": datetime.now(UTC).isoformat(),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "code_cells": sum(cell.cell_type == "code" for cell in notebook.cells),
        }
        try:
            check_offline_defaults(notebook)
            NotebookClient(
                notebook, timeout=90, resources={"metadata": {"path": str(ROOT)}}
            ).execute(env=environment)
            result["cleanup_local"] = cleanup_status(notebook, "cleanup_local", "cleanup_local")
            result["cleanup_cloud"] = cleanup_status(notebook, "cleanup_cloud", "cloud_cleanup")
            if result["cleanup_local"] != "PASS" or result["cleanup_cloud"] != "NOT_RUN":
                raise ValueError("Resultado inesperado no cleanup offline")
            result["status"] = "PASS"
        except Exception as exc:
            result["error_type"] = type(exc).__name__
            result["error_message"] = str(exc)[:1500]
            # Os detalhes da falha ficam na célula da cópia executada.
        finally:
            result["executed_code_cells"] = sum(
                cell.cell_type == "code" and cell.execution_count is not None
                for cell in notebook.cells
            )
            result["elapsed_seconds"] = round(time.monotonic() - started, 2)
            nbformat.write(notebook, out / path.name)
            results.append(result)
            (ROOT / "evidence/notebooks.json").write_text(json.dumps(results, indent=2) + "\n")
        print(
            f"{path.name}: {result['status']} "
            f"({result['executed_code_cells']}/{result['code_cells']} células; "
            f"cleanup local={result.get('cleanup_local', 'NOT_RUN')})",
            flush=True,
        )
    if any(result["status"] != "PASS" for result in results):
        raise SystemExit("Falhas registradas em evidence/notebooks.json e evidence/executed/")


if __name__ == "__main__":
    main()
