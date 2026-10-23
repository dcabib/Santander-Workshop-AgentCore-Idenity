"""Injeta falhas apenas em kernels isolados; o notebook deve rejeitar a causa exata."""

import hashlib
import json
import os
import re
from datetime import UTC, datetime

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

from scripts.audit_notebooks import ROOT
from scripts.verify_notebooks import check_offline_defaults

FAULTS = [
    (
        "rag_managed_identity_policy",
        "C perde Fraude na configuração de permissões",
        'from santander_demo.rag.contract import DOMAINS\nDOMAINS["c"] = ("riscos",)',
        "ACL do corpus diverge da matriz prevista",
    ),
    (
        "gateway_targets",
        "MCP retorna outro cliente e dados vazios, com isError=False",
        """import json
from mcp import ClientSession
from mcp.types import TextContent
_actual_call = ClientSession.call_tool
async def _wrong_payload(self, *args, **kwargs):
    result = await _actual_call(self, *args, **kwargs)
    wrong = {"cliente_id": "CLIENTE_ERRADO", "synthetic": True,
             "tool": "fraude___consultar_fraude", "dados": []}
    result.structuredContent = wrong
    result.content = [TextContent(type="text", text=json.dumps(wrong))]
    return result
ClientSession.call_tool = _wrong_payload
""",
        "O conteúdo MCP diverge da consulta descrita",
    ),
    (
        "gateways_por_conta_identity_policy",
        "Relatório alega permissão Retail para C008",
        """from santander_demo.federation import spec
_actual_matrix = spec.local_matrix
def _wrong_matrix():
    result = _actual_matrix()
    row = next(r for r in result["cases"] if r["customer"] == "C008")
    row["retail_policy_isolated"] = "ALLOW"
    row["end_to_end_contract"] = "ALLOW"
    return result
spec.local_matrix = _wrong_matrix
""",
        "As decisões divergem da matriz descrita",
    ),
]


def main():
    results = []
    output = ROOT / "evidence/notebook-fault-regressions.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text("[]\n")
    for suffix, description, injection, expected_error in FAULTS:
        path, = (ROOT / "notebooks").glob(f"*_{suffix}.ipynb")
        notebook = nbformat.read(path, as_version=4)
        check_offline_defaults(notebook)
        first = next(i for i, c in enumerate(notebook.cells) if c.cell_type == "code")
        notebook.cells[first:first] = [
            nbformat.v4.new_markdown_cell("Falha intencional, somente neste kernel."),
            nbformat.v4.new_code_cell(
                "from scripts.audit_notebooks import Observer\n"
                f"_observer = Observer({suffix!r}, 'fault').start()\n" + injection
            ),
        ]
        result = {
            "notebook": path.name,
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "tested_at": datetime.now(UTC).isoformat(),
            "fault": description,
            "expected_assertion": expected_error,
            "status": "FAIL",
        }
        try:
            NotebookClient(
                notebook, timeout=180, resources={"metadata": {"path": str(ROOT)}}
            ).execute(env=dict(os.environ, WORKSHOP_MODE="local", AWS_EC2_METADATA_DISABLED="true"))
        except CellExecutionError as exc:
            result["actual_error"] = exc.ename
            # Uma falha incidental de import/rede/sintaxe não aprova este controle.
            trace = re.sub(r"\x1b\[[0-9;]*m", "", exc.traceback)
            exact_assertion = exc.ename == "AssertionError" and expected_error == exc.evalue
            nested_assertion = (
                exc.ename == "ExceptionGroup"
                and f"AssertionError: {expected_error}" in trace
            )
            if exact_assertion or nested_assertion:
                result["status"] = "FAULT_REJECTED"
        results.append(result)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        print(f"{path.name}: {result['status']}", flush=True)
    if any(r["status"] != "FAULT_REJECTED" for r in results):
        raise SystemExit("Uma falha injetada não foi rejeitada pela asserção esperada")


if __name__ == "__main__":
    main()
