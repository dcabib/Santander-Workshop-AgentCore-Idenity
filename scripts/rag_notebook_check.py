"""Executa o lab 16 em kernel novo; --live usa o IaC existente, sem provisionar."""

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from nbclient import NotebookClient

from scripts.verify_notebooks import check_offline_defaults, cleanup_status

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "notebooks/16_rag_managed_identity_policy.ipynb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    notebook = nbformat.read(SOURCE, as_version=4)
    check_offline_defaults(notebook)
    if args.live:
        settings = [c for c in notebook.cells if "RUN_AWS = False" in c.source]
        if len(settings) != 1:
            raise ValueError("EXPECTED_ONE_AWS_SWITCH")
        settings[0].source = settings[0].source.replace("RUN_AWS = False", "RUN_AWS = True")
    mode = "AWS_LIVE" if args.live else "LOCAL_CONTRACT"
    report = {
        "notebook": SOURCE.name,
        "mode": mode,
        "started_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "code_cells": sum(c.cell_type == "code" for c in notebook.cells),
        "status": "FAIL",
    }
    started = time.monotonic()
    try:
        NotebookClient(notebook, timeout=300, resources={"metadata": {"path": str(ROOT)}}).execute(
            env=dict(os.environ, AWS_EC2_METADATA_DISABLED="true")
        )
        report["cleanup_local"] = cleanup_status(notebook, "cleanup_local", "cleanup_local")
        report["cleanup_cloud"] = cleanup_status(notebook, "cleanup_cloud", "cloud_cleanup")
        if report["cleanup_local"] != "PASS" or report["cleanup_cloud"] != "NOT_RUN":
            raise ValueError("UNEXPECTED_CLEANUP")
        if args.live:
            evidence = json.loads((ROOT / "evidence/rag-live.json").read_text())
            if (
                evidence["started_ms"]
                < datetime.fromisoformat(report["started_at"]).timestamp() * 1000
            ):
                raise ValueError("STALE_LIVE_EVIDENCE")
            report["aws_acceptance"] = evidence["acceptance"]
            report["status"] = evidence["acceptance"]["status"]
        else:
            report["status"] = "PASS"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        # A cópia executada não é persistida: pode conter contexto de autenticação.
        print(f"Falha ao executar o notebook: {type(exc).__name__}", flush=True)
        raise
    finally:
        report["executed_code_cells"] = sum(
            c.cell_type == "code" and c.execution_count is not None for c in notebook.cells
        )
        report["elapsed_seconds"] = round(time.monotonic() - started, 2)
        destination = ROOT / "evidence" / f"rag-notebook-{'live' if args.live else 'local'}.json"
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
