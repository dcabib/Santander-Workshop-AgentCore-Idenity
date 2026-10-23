"""Executa o notebook 09; --live valida AWS já implantada, sem apply ou cleanup."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from verify_notebooks import check_offline_defaults, cleanup_status

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "notebooks/09_terraform_runtime_gateway_identity.ipynb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Usa config/local.terraform.json")
    args = parser.parse_args()
    os.umask(0o077)
    notebook = nbformat.read(SOURCE, as_version=4)
    check_offline_defaults(notebook)
    if args.live:
        if not (ROOT / "config/local.terraform.json").is_file():
            raise FileNotFoundError("Configure config/local.terraform.json e implante primeiro")
        for cell in notebook.cells:
            if cell.cell_type == "code":
                cell.source = cell.source.replace("RUN_AWS = False", "RUN_AWS = True")
                cell.source = cell.source.replace("RUN_AGENT = False", "RUN_AGENT = True")
    mode = "AWS_LIVE" if args.live else "LOCAL_CODE_AND_PROTOCOL_TESTS"
    suffix = "aws" if args.live else "local"
    out = ROOT / "evidence/executed" / f"{SOURCE.stem}.{suffix}.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "evidence" / f"terraform-notebook-{suffix}.json"
    report = {
        "status": "RUNNING",
        "mode": mode,
        "started_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "executed_notebook": str(out.relative_to(ROOT)),
        "deploy_and_destroy": "DISABLED",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    try:
        NotebookClient(
            notebook, timeout=600,
            resources={"metadata": {"path": str(ROOT)}},
        ).execute()
        report["cleanup_local"] = cleanup_status(notebook, "cleanup_local", "cleanup_local")
        report["cleanup_cloud"] = cleanup_status(notebook, "cleanup_cloud", "cloud_cleanup")
        if report["cleanup_local"] != "PASS" or report["cleanup_cloud"] != "NOT_RUN":
            raise RuntimeError("UNEXPECTED_NOTEBOOK_CLEANUP")
        report["status"] = "PASS"
    except Exception as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["executed_code_cells"] = sum(
            c.cell_type == "code" and c.execution_count is not None for c in notebook.cells
        )
        nbformat.write(notebook, out)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
