"""Executa as células SDK no ambiente de notebooks AWS e registra evidências."""

import argparse
import ast
import getpass
import hashlib
import json
import os
import re
import time
import warnings
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import boto3
import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
SDK_LABS = ("00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "15", "16", "99")


@contextmanager
def session_credentials(prompt=False):
    """Credenciais temporárias por entrada oculta, somente na memória do processo."""
    if not prompt:
        yield
        return
    keys = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")
    with warnings.catch_warnings():
        # getpass pode recorrer a entrada com eco se o terminal não for compatível.
        warnings.simplefilter("error", getpass.GetPassWarning)
        values = {key: getpass.getpass(key + " (entrada oculta): ") for key in keys}
    if (
        not re.fullmatch(r"ASIA[A-Z0-9]{16}", values["AWS_ACCESS_KEY_ID"])
        or len(values["AWS_SECRET_ACCESS_KEY"]) != 40
        or not values["AWS_SESSION_TOKEN"]
        or any("\n" in value or "\r" in value for value in values.values())
    ):
        raise ValueError("AWS_TEMPORARY_SESSION_CREDENTIALS_REQUIRED")
    managed = (*keys, "AWS_PROFILE", "AWS_DEFAULT_PROFILE")
    previous = {key: os.environ.get(key) for key in managed}
    try:
        os.environ.update(values)
        for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        values.clear()


def selection(root, labs):
    """Confere toda a seleção antes de abrir o primeiro kernel."""
    if len(labs) != len(set(labs)) or list(labs) != sorted(labs):
        raise ValueError("SDK_LABS_REQUIRE_UNIQUE_ORDER: 00, 01, ...; 99 por último.")
    paths = []
    for lab in labs:
        matches = list((root / "notebooks").glob(lab + "_*.ipynb"))
        if len(matches) != 1:
            raise ValueError("SDK_NOTEBOOK_FILE_REQUIRED: " + lab)
        notebook = nbformat.read(matches[0], as_version=4)
        nbformat.validate(notebook)
        if notebook.metadata.get("workshop", {}).get("provisioning") != "NOTEBOOK_SDK":
            raise ValueError("SDK_MIGRATION_REQUIRED: " + lab)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                compile(cell.source, str(matches[0]), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
        paths.append(matches[0])
    return paths


def redact(value, environment):
    """Evita incluir credenciais da sessão ou JWTs nos artefatos de execução."""
    if isinstance(value, dict):
        return {key: redact(child, environment) for key, child in value.items()}
    if isinstance(value, list):
        return [redact(child, environment) for child in value]
    if not isinstance(value, str):
        return value
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        secret = environment.get(key)
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"\b(?:ASIA|AKIA)[A-Z0-9]{16}\b", "[REDACTED]", value)
    return re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED]", value)


def execute(root, paths, *, account, region, output, validate_only=False, timeout=900):
    environment = {
        **os.environ,
        "AWS_DEFAULT_REGION": region,
        "AWS_REGION": region,
        "WORKSHOP_EXPECTED_ACCOUNT": account,
    }
    output.mkdir(parents=True, exist_ok=True)
    results = []

    def report():
        (output / "report.json").write_text(
            json.dumps(redact(results, environment), indent=2, ensure_ascii=False) + "\n",
        )

    if not validate_only:
        try:
            identity = boto3.Session(region_name=region).client("sts").get_caller_identity()
            if identity["Account"] != account:
                raise ValueError("WORKSHOP_ACCOUNT_MISMATCH")
        except Exception as error:
            results.extend({
                "notebook": path.name, "status": "BLOCKED", "validation": "AWS_PREFLIGHT",
                "account": account, "region": region,
                "error_type": type(error).__name__,
                "error_code": getattr(error, "response", {}).get("Error", {}).get("Code"),
            } for path in paths)
            report()
            raise
    else:
        identity = None

    for path in paths:
        notebook = nbformat.read(path, as_version=4)
        start = time.monotonic()
        row = {
            "notebook": path.name, "status": "FAIL",
            "validation": "STATIC_ONLY" if validate_only else "AWS_EXECUTION",
            "account": account, "region": region,
            "started_at": datetime.now(UTC).isoformat(),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "code_cells": sum(cell.cell_type == "code" for cell in notebook.cells),
        }
        if identity:
            row.update(
                principal=identity["Arn"],
                sts_request_id=identity["ResponseMetadata"]["RequestId"],
            )

        def progress(notebook_name=path.name, **kwargs):
            print(f"{notebook_name}: célula {kwargs['cell_index']}", flush=True)

        try:
            if not validate_only:
                NotebookClient(
                    notebook, timeout=timeout, kernel_name="santander-workshop",
                    resources={"metadata": {"path": str(root)}},
                    on_cell_execute=progress,
                ).execute(env=environment)
                if any(
                    cell.execution_count is None
                    for cell in notebook.cells if cell.cell_type == "code"
                ):
                    raise ValueError("INCOMPLETE_NOTEBOOK_EXECUTION")
                if any(
                    item.get("output_type") == "error"
                    for cell in notebook.cells if cell.cell_type == "code"
                    for item in cell.outputs
                ):
                    raise ValueError("NOTEBOOK_EXECUTION_ERRORS")
            row["status"] = "VALID" if validate_only else "PASS"
        except Exception as error:
            row["error_type"] = type(error).__name__
            errors = [
                (index, item)
                for index, cell in enumerate(notebook.cells) if cell.cell_type == "code"
                for item in cell.outputs if item.get("output_type") == "error"
            ]
            if errors:
                index, last = errors[-1]
                row.update(
                    cell_index=index, error_type=last.get("ename"),
                    error_message=redact(last.get("evalue", ""), environment)[:1500],
                )
        finally:
            row["elapsed_seconds"] = round(time.monotonic() - start, 2)
            if not validate_only:
                # As fontes permanecem intactas; somente saídas são higienizadas.
                for cell in notebook.cells:
                    if cell.cell_type == "code":
                        cell.outputs = [nbformat.from_dict(redact(item, environment)) for item in cell.outputs]
                nbformat.write(notebook, output / path.name)
            results.append(row)
            report()
        print(f"{path.name}: {row['status']} ({row['validation']})", flush=True)
        if row["status"] == "FAIL":
            break
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labs", nargs="+", required=True, choices=SDK_LABS,
                        help="Células executadas na ordem indicada; inclua 99 somente para limpar.")
    parser.add_argument("--expected-account", help="ID da conta efêmera autorizada para esta execução.")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--output", type=Path, help="Diretório das evidências; padrão: build/notebook-runs.")
    parser.add_argument("--validate-only", action="store_true", help="Somente formato/sintaxe; não é aceite AWS.")
    parser.add_argument(
        "--prompt-credentials", action="store_true",
        help="Ler uma sessão temporária em entrada oculta, sem arquivos ou histórico do shell.",
    )
    parser.add_argument(
        "--cleanup-scope", choices=("all", "rag-runtime"),
        help="Somente com --labs 99; rag-runtime preserva a base, fonte, conector e demais aulas.",
    )
    args = parser.parse_args()
    if not args.validate_only and not re.fullmatch(r"\d{12}", args.expected_account or ""):
        parser.error("--expected-account é obrigatório e precisa conter os 12 dígitos da conta.")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", args.region):
        parser.error("Região inválida.")
    if args.validate_only and args.prompt_credentials:
        parser.error("--validate-only não usa credenciais.")
    if args.cleanup_scope and args.labs != ["99"]:
        parser.error("--cleanup-scope exige a seleção exclusiva --labs 99.")
    try:
        paths = selection(ROOT, args.labs)
    except ValueError as error:
        parser.error(str(error))
    output = args.output or ROOT / "build/notebook-runs" / (
        (args.expected_account or "static") + "-" + args.region + "-"
        + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    )
    with session_credentials(args.prompt_credentials):
        previous_scope = os.environ.get("WORKSHOP_CLEANUP_SCOPE")
        try:
            if args.cleanup_scope:
                os.environ["WORKSHOP_CLEANUP_SCOPE"] = args.cleanup_scope
            results = execute(
                ROOT, paths, account=args.expected_account or "", region=args.region,
                output=output, validate_only=args.validate_only,
            )
        finally:
            if previous_scope is None:
                os.environ.pop("WORKSHOP_CLEANUP_SCOPE", None)
            else:
                os.environ["WORKSHOP_CLEANUP_SCOPE"] = previous_scope
    print("Evidências: " + str(output / "report.json"))
    if any(row["status"] in {"FAIL", "BLOCKED"} for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
