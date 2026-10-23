"""Audita resultados observados nos kernels, sem aceitar os flags PASS como oráculo.

Os oráculos abaixo transcrevem requisitos didáticos, não a configuração de acesso.
As cópias instrumentadas ficam em memória; somente observações locais selecionadas
são exportadas. Este comando nunca habilita AWS, deploy, build ou remoção.
"""

import argparse
import copy
import hashlib
import json
import os
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = {
    "preflight": "00",
    "gateway_targets": "01",
    "identity_entra_obo": "02",
    "identity_agente_mcp": "03",
    "policy_cedar": "04",
    "policy_autoria": "05",
    "registry_governanca": "06",
    "registry_personas": "registry",
    "registry_descoberta_execucao": "07",
    "santander_multi_conta": "08",
    "databricks_e_evidencias": "09",
    "blog_multi_account_gateway_mcp": "10",
    "gateways_por_conta_identity_policy": "11",
    "cenario_santander_integrado": "12",
    "ingestao_acl_memoria": "13",
    "rag_managed_identity_policy": "14",
    "terraform_runtime_gateway_identity": "15",
}
RAG_DOCUMENTS = {
    "a": ["R1", "R2"],
    "b": ["F1", "F2"],
    "c": ["F1", "F2", "R1", "R2"],
    "d": [],
}
CORE_TOOLS = [
    "fraude___consultar_fraude",
    "riscos___consultar_conhecimento_k2",
    "riscos___consultar_risco",
]
POLICY_OUTCOMES = [
    "ALLOW",
    "POLICY_DENY",
    "POLICY_DENY",
    "ALLOW",
    "POLICY_DENY",
    "SCHEMA_INVALID",
    "UNKNOWN_TOOL",
    "POLICY_DENY",
    "POLICY_DENY",
    "AUTH_INVALID_TOKEN",
    "AUTH_INVALID_TOKEN",
    "POLICY_DENY",
]
LIVE_SCOPE = {
    **dict.fromkeys(
        ("00", "01", "02", "03", "04", "05", "06", "07", "08", "09"),
        "NOT_RUN: config/local.json, contas e identidades Entra ausentes; "
        "Graph/Databricks também exigem seus ambientes e usuários",
    ),
    "10": "NOT_RUN: quatro contas, aplicações Okta e KB Lending não configuradas",
    "11": "NOT_RUN: quatro contas, aplicações Entra e KB Lending não configuradas",
    "12": "NOT_RUN: três contas, aplicações Entra e Databricks não configurados",
    "13": "NOT_APPLICABLE: o notebook declara somente contrato local",
    "14": "SEPARATE_RUN_REQUIRED: auditar evidência AWS e logs do ambiente RAG",
    "15": "SEPARATE_RUN_REQUIRED: auditar evidência AWS e logs do ambiente Terraform",
    "registry": "SEPARATE_RUN_REQUIRED: consumo AWS e simulação IAM; transições exigem ciclo IaC",
}


def mcp_payload(result):
    """Lê o conteúdo, não a marca isError ou um flag de sucesso da aplicação."""
    body = result.structuredContent
    if body is None:
        texts = [json.loads(block.text) for block in result.content if block.type == "text"]
        if len(texts) != 1:
            raise ValueError("EXPECTED_ONE_MCP_JSON_RESULT")
        body = texts[0]
    return body


class Observer:
    """Observa chamadas reais dos objetos locais sem substituir seus resultados."""

    def __init__(self, scenario, notebook_id):
        self.scenario = scenario
        self.notebook_id = notebook_id
        self.stack = ExitStack()
        self.backend_calls = []
        self.cedar_decisions = []
        self.knowledge_calls = []
        self.quota_calls = []
        self.cloud_attempts = []
        self.registry_risk_calls = []
        self.checks = []
        self.started_at = datetime.now(UTC).isoformat()

    def start(self):
        import cedarpy
        from botocore.client import BaseClient

        from santander_demo import backends
        from santander_demo.governance import LocalQuotaLedger
        from santander_demo.knowledge import KnowledgeLab

        original_execute = backends.execute

        def execute(tool, arguments):
            # Medir a entrada no backend, inclusive quando ele levanta uma exceção.
            entry = {"tool": tool, "arguments": copy.deepcopy(arguments)}
            self.backend_calls.append(entry)
            result = original_execute(tool, arguments)
            entry["result"] = copy.deepcopy(result)
            return result

        original_cedar = cedarpy.is_authorized

        def cedar(*args, **kwargs):
            result = original_cedar(*args, **kwargs)
            request = args[0]
            self.cedar_decisions.append(
                {
                    "action": request["action"]["id"],
                    "resource": request["resource"]["id"],
                    "allowed": result.allowed,
                }
            )
            return result

        def no_cloud(client, operation, parameters):
            self.cloud_attempts.append(operation)
            raise AssertionError("AWS_API_ATTEMPT_IN_OFFLINE_NOTEBOOK")

        self.stack.enter_context(patch.object(backends, "execute", execute))
        self.stack.enter_context(patch.object(cedarpy, "is_authorized", cedar))
        self.stack.enter_context(patch.object(BaseClient, "_make_api_call", no_cloud))
        for name in ("register", "update", "delete", "retrieve", "remember", "recall"):
            original = getattr(KnowledgeLab, name)

            def observe(instance, *args, _name=name, _original=original, **kwargs):
                result = _original(instance, *args, **kwargs)
                self.knowledge_calls.append(
                    {
                        "operation": _name,
                        "result": copy.deepcopy(result),
                        "documents": sorted(instance.documents),
                        "memory": {str(k): list(v) for k, v in instance.memory.items()},
                    }
                )
                return result

            self.stack.enter_context(patch.object(KnowledgeLab, name, observe))
        original_reserve = LocalQuotaLedger.reserve

        def reserve(instance, *args, **kwargs):
            before = (copy.deepcopy(instance.minute), copy.deepcopy(instance.month))
            result = original_reserve(instance, *args, **kwargs)
            self.quota_calls.append(
                {
                    "decision": result["decision"],
                    "state_changed": before != (instance.minute, instance.month),
                }
            )
            return result

        self.stack.enter_context(patch.object(LocalQuotaLedger, "reserve", reserve))
        if self.scenario == "registry_personas":
            from santander_demo.registry_workflow import contracts

            original_risk = contracts.risk

            def risk(arguments):
                result = original_risk(arguments)
                self.registry_risk_calls.append(copy.deepcopy(result))
                return result

            self.stack.enter_context(patch.object(contracts, "risk", risk))
        return self

    def equal(self, claim, observed, expected):
        self.checks.append(
            {
                "claim": claim,
                "expected": expected,
                "observed": observed,
                "matched": observed == expected,
            }
        )

    def core_matrix(self, lab):
        self.equal(
            "12 decisões observadas, sem usar rows.passed",
            [e["outcome"] for e in lab.evidence.events],
            POLICY_OUTCOMES,
        )
        self.equal(
            "Somente os dois casos permitidos entraram no backend",
            [c["tool"] for c in self.backend_calls],
            ["riscos___consultar_risco", "fraude___consultar_fraude"],
        )
        self.equal(
            "Cedar executou de fato nos oito casos que passaram JWT/schema/tool",
            [c["allowed"] for c in self.cedar_decisions],
            [True, False, False, True, False, False, False, False],
        )

    def inspect(self, ns):
        prefix = SCENARIOS[self.scenario]
        self.equal("Nenhuma API AWS no caminho local", self.cloud_attempts, [])
        if prefix in {"00", "01", "02", "03", "04", "05", "06", "07", "08", "09"}:
            lab = ns["lab"]
            self.equal(
                "Catálogo local com os três contratos descritos",
                sorted(t["name"] for t in lab.tools()),
                CORE_TOOLS,
            )
            self.equal("Modo local explícito", ns["MODE"], "local")
        if prefix == "00":
            self.equal("Preflight não invocou backend", self.backend_calls, [])
            self.equal(
                "Versões das quatro bibliotecas foram consultadas",
                sorted(ns["versions"]),
                ["boto3", "cedarpy", "mcp", "pyjwt"],
            )
        elif prefix == "01":
            body = mcp_payload(ns["answer"])
            self.equal(
                "MCP retornou a consulta Fraude do cliente e conteúdo esperados",
                body,
                {
                    "cliente_id": "SANT-DEMO-001",
                    "synthetic": True,
                    "tool": "fraude___consultar_fraude",
                    "dados": [{"indicios": ["dispositivo_novo"], "revisao": "manual"}],
                },
            )
        elif prefix == "02":
            from santander_demo.contracts import DemoError

            observed = "TOKEN_ACCEPTED"
            try:
                ns["wrong_audience"].verify(ns["token"])
            except DemoError as exc:
                observed = exc.code
            self.equal(
                "Repetição independente rejeitou audiência Graph", observed, "AUTH_INVALID_TOKEN"
            )
            self.equal("Sem backend/OBO na prova local", self.backend_calls, [])
        elif prefix == "03":
            first = lab.idp.verifier.verify(ns["permitted"]).claims
            second = lab.idp.verifier.verify(ns["restricted"]).claims
            self.equal(
                "Mesmo usuário, dois chamadores assinados",
                [first["oid"], second["oid"], first["azp"], second["azp"]],
                ["user-ambos", "user-ambos", "supervisor", "riscos"],
            )
            self.equal(
                "Só o supervisor chegou ao backend",
                [c["tool"] for c in self.backend_calls],
                ["fraude___consultar_fraude"],
            )
            self.equal(
                "Cedar permitiu e negou de fato",
                [c["allowed"] for c in self.cedar_decisions],
                [True, False],
            )
        elif prefix in {"04", "05", "09"}:
            self.core_matrix(lab)
            if prefix == "09":
                actual = json.loads((ROOT / "evidence/local-notebook.json").read_text())
                self.equal(
                    "Arquivo exportado corresponde aos eventos observados",
                    actual["events"],
                    lab.evidence.events,
                )
                self.equal("Prova Databricks não foi inventada", ns["proof"], None)
        elif prefix == "06":
            self.equal(
                "Registro do exercício terminou aprovado",
                lab.registry.records["exercicio"].state,
                "APPROVED",
            )
            self.equal(
                "Busca só expõe a proposta aprovada",
                [r["name"] for r in lab.registry.search("proposta")],
                ["exercicio"],
            )
            self.equal(
                "Rascunhos e rejeitados não aparecem em busca vazia",
                sorted({r["state"] for r in lab.registry.search("")}),
                ["APPROVED"],
            )
        elif prefix == "registry":
            self.equal(
                "MCP e AGENT v1 aprovados; nova versão rejeitada",
                sorted(
                    (kind, version, record["status"])
                    for (kind, version), record in ns["flow"].records.items()
                ),
                [
                    ("AGENT", "1.0.0", "APPROVED"),
                    ("AGENT", "1.1.0", "REJECTED"),
                    ("MCP", "1.0.0", "APPROVED"),
                ],
            )
            self.equal(
                "Duas fixtures do desenvolvedor e só uma execução do consumidor chegaram à regra",
                self.registry_risk_calls,
                [
                    {"customer_id": "C001", "risk": "baixo"},
                    {"customer_id": "C002", "risk": "alto"},
                    {"customer_id": "C001", "risk": "baixo"},
                ],
            )
            self.equal(
                "Resposta do agente reflete a chamada de C001",
                ns["result"]["answer"],
                "Cliente C001: risco baixo.",
            )
            self.equal(
                "Consumidor só descobre a versão aprovada",
                sorted((r["recordType"], r["recordVersion"]) for r in ns["flow"].discover()),
                [("AGENT", "1.0.0"), ("MCP", "1.0.0")],
            )
        elif prefix == "07":
            actual = {r["tool"]: r for r in ns["result"]["results"]}
            self.equal("Descoberta retornou três resultados", sorted(actual), CORE_TOOLS)
            self.equal(
                "Somente Riscos/K2 chegaram ao backend",
                [c["tool"] for c in self.backend_calls],
                ["riscos___consultar_risco", "riscos___consultar_conhecimento_k2"],
            )
            self.equal(
                "Fraude encontrada mas recusada",
                actual["fraude___consultar_fraude"],
                {
                    "tool": "fraude___consultar_fraude",
                    "outcome": "POLICY_DENY",
                },
            )
            self.equal(
                "K2 é explicitamente uma fixture",
                actual["riscos___consultar_conhecimento_k2"]["dados"][0]["integracao_k2"],
                False,
            )
        elif prefix == "08":
            self.equal("Topologia declarada não foi promovida a invocação", self.backend_calls, [])
        elif prefix == "10":
            self.inspect_banking(ns)
        elif prefix == "11":
            self.equal(
                "Três decisões da matriz correspondem ao texto",
                [
                    [r["customer"], r["platform_policy"], r["retail_policy_isolated"]]
                    for r in ns["matrix"]["cases"]
                ],
                [["C003", "ALLOW", "ALLOW"], ["C007", "DENY", "ALLOW"], ["C008", "ALLOW", "DENY"]],
            )
            self.equal(
                "Avaliador Cedar foi executado para as seis decisões",
                [c["allowed"] for c in self.cedar_decisions],
                [True, True, False, True, True, False],
            )
            paths = sorted((ROOT / "infra/federation/templates").glob("*-gateway.json"))
            self.equal(
                "Quatro Gateways declarados com enforcement",
                [
                    json.loads(p.read_text())["Resources"]["Gateway"]["Properties"][
                        "PolicyEngineConfiguration"
                    ]["Mode"]
                    for p in paths
                ],
                ["ENFORCE"] * 4,
            )
            self.equal("Nenhuma resposta de LOB foi produzida offline", ns["observations"], {})
        elif prefix == "12":
            self.equal(
                "Oito decisões Cedar conforme os oito casos descritos",
                [r["decision"] for r in ns["matrix"]["cases"]],
                ["ALLOW", "DENY", "DENY", "ALLOW", "ALLOW", "DENY", "DENY", "DENY"],
            )
            self.equal(
                "Oito avaliações realmente executadas",
                [c["allowed"] for c in self.cedar_decisions],
                [True, False, False, True, True, False, False, False],
            )
            self.equal(
                "Decisões observadas do ledger",
                [c["decision"] for c in self.quota_calls],
                ["ALLOW", "ALLOW", "QPM_DENY", "TPM_DENY", "BUDGET_DENY"],
            )
            self.equal(
                "O relatório de cotas exibido corresponde às decisões reais",
                [r["decision"] for r in ns["quota_demo"]],
                [c["decision"] for c in self.quota_calls],
            )
            self.equal(
                "Negativas não debitam contadores",
                [c["state_changed"] for c in self.quota_calls],
                [True, True, False, False, False],
            )
            self.equal("Sem consultas Databricks inventadas", ns["report"]["calls"], [])
            self.equal(
                "Aceite incompleto não foi promovido a PASS",
                ns["report"]["acceptance"]["status"],
                "PENDING_EVIDENCE",
            )
        elif prefix == "13":
            self.inspect_knowledge(ns)
        elif prefix == "14":
            self.inspect_rag(ns)
        elif prefix == "15":
            self.equal(
                "Dois saldos e identidades correspondem às fixtures do texto",
                [[r["customer_id"], r["balance_brl"]] for r in ns["local_profiles"]],
                [["C001", "1250.00"], ["C002", "8700.00"]],
            )
            self.equal(
                "Handler local devolveu o perfil correto",
                [ns["local_result"]["customer_id"], ns["local_result"]["balance_brl"]],
                ["C001", "1250.00"],
            )
            self.equal(
                "IDs do handler correspondem ao contexto fictício, sem alegar AWS",
                ns["local_result"]["execution"],
                {
                    "gateway_request_id": "LOCAL_GATEWAY_REQUEST",
                    "lambda_request_id": "LOCAL_LAMBDA_REQUEST",
                    "tool": "banking___get_customer_profile",
                },
            )
        result = {
            "notebook_id": self.notebook_id,
            "scenario": self.scenario,
            "observed_at": datetime.now(UTC).isoformat(),
            "scope": "LOCAL_OBSERVATIONS",
            "checks": self.checks,
            "aws_scope": LIVE_SCOPE[prefix],
            "status": "MATCH"
            if self.checks and all(c["matched"] for c in self.checks)
            else "MISMATCH",
        }
        (ROOT / "evidence" / f"notebook-audit-{self.notebook_id}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        self.stack.close()
        if result["status"] != "MATCH":
            raise AssertionError("NOTEBOOK_CONTENT_OBSERVATION_MISMATCH")
        print(json.dumps({"independent_audit": result["status"], "claims": len(self.checks)}))

    def inspect_banking(self, ns):
        schemas = ns["schemas"]
        self.equal(
            "16 ferramentas nos três contratos locais",
            sum(len(tools) for tools in schemas.values()),
            16,
        )
        self.equal(
            "Três áreas de negócio",
            sorted(schemas),
            ["lending-wealth", "retail-banking", "transaction-banking"],
        )
        bindings = json.loads((ROOT / "infra/banking/templates/bindings.json").read_text())
        policies = {
            name
            for name, resource in bindings["Resources"].items()
            if resource["Type"] == "AWS::BedrockAgentCore::Policy"
        }
        self.equal(
            "IaC publica apenas leitura e proibição de exclusão",
            sorted(policies),
            ["NeverDelete", "ReadTools"],
        )
        self.equal(
            "Sem respostas ou inferência inventadas",
            [ns["observations"], ns["agent_result"]],
            [{}, None],
        )

    def inspect_knowledge(self, ns):
        self.equal(
            "O relatório de visibilidade exibido corresponde aos três usuários",
            ns["knowledge_report"]["visibility_before"],
            {"user-riscos": ["R1"], "user-fraude": ["F1"], "user-ambos": ["R1", "F1"]},
        )
        self.equal(
            "Quatro fontes de contrato, nenhuma ingestão externa",
            [[s["source"], s["live_ingestion"]] for s in ns["sources"]],
            [
                [s, False]
                for s in ["SharePoint", "Databricks Silver/Gold", "SQL on-prem", "AWS API"]
            ],
        )
        queries = [c for c in self.knowledge_calls if c["operation"] == "retrieve"]
        self.equal(
            "Visibilidade real de Riscos, Fraude e Ambos antes da revogação",
            [[r["document_id"] for r in c["result"]] for c in queries[:3]],
            [["R1"], ["F1"], ["R1", "F1"]],
        )
        self.equal(
            "Duas leituras reais de memória negadas",
            [c["result"] for c in self.knowledge_calls if c["operation"] == "recall"],
            [[], []],
        )
        self.equal(
            "Memória mantém IDs, sem copiar o conteúdo",
            [c["memory"] for c in self.knowledge_calls if c["operation"] == "remember"],
            [{"('user-riscos', 'same-session')": ["R1"]}],
        )
        self.equal(
            "F1 removido do índice e da última busca",
            [queries[-1]["documents"], [r["document_id"] for r in queries[-1]["result"]]],
            [["R1"], ["R1"]],
        )
        self.equal(
            "Quatro alterações reais no ciclo de vida",
            [
                c["operation"]
                for c in self.knowledge_calls
                if c["operation"] in {"register", "update", "delete"}
            ],
            ["register", "register", "update", "delete"],
        )
        self.equal(
            "Auditoria do helper descreve essas mesmas operações",
            [r["operation"] for r in ns["knowledge_report"]["lifecycle"]],
            ["register", "register", "update", "delete"],
        )

    def inspect_rag(self, ns):
        lab = ns["lab"]
        actual = {row["case"]: sorted(row["document_ids"]) for row in ns["matrix"]}
        self.equal("A/B/C/D correspondem à tabela didática, sem ler DOMAINS", actual, RAG_DOCUMENTS)
        # As três primeiras chamadas correspondem aos casos A/B/C; D não chama modelo.
        contexts = []
        for request in lab.model.calls[:3]:
            payload = json.loads(request["messages"][0]["content"][0]["text"])
            contexts.append(sorted(chunk["id"] for chunk in payload["trechos_autorizados"]))
        self.equal(
            "Conteúdo efetivamente entregue ao modelo para A/B/C",
            contexts,
            [RAG_DOCUMENTS[k] for k in "abc"],
        )
        self.equal(
            "D não chegou à KB nem ao modelo",
            [
                [r["retrieval_calls"], r["generation_calls"]]
                for r in ns["matrix"]
                if r["case"] == "d"
            ],
            [[0, 0]],
        )
        self.equal(
            "Tentativa A→C não chegou à KB nem ao modelo",
            [
                ns["spoof"]["policy"],
                ns["spoof"]["retrieval_calls"],
                ns["spoof"]["generation_calls"],
            ],
            ["DENY", 0, 0],
        )
        self.equal(
            "Somente A/B/C e repetição do prompt de A consultaram a KB",
            [c["userContext"]["userId"] for c in lab.kb.calls],
            ["a@example.invalid", "b@example.invalid", "c@example.invalid", "a@example.invalid"],
        )
        self.equal(
            "Corpo da resposta local C contém os quatro documentos",
            [f"[{doc}]" in ns["matrix"][2]["answer"] for doc in RAG_DOCUMENTS["c"]],
            [True] * 4,
        )


def run(selected=None):
    import nbformat
    from nbclient import NotebookClient

    from scripts.verify_notebooks import check_offline_defaults, cleanup_status

    results = []
    aggregate = ROOT / "evidence/notebook-audit.json"
    aggregate.parent.mkdir(exist_ok=True)
    aggregate.write_text("[]\n")
    environment = dict(os.environ, WORKSHOP_MODE="local", AWS_EC2_METADATA_DISABLED="true")
    environment.pop("RUN_DATABRICKS", None)
    for path in sorted((ROOT / "notebooks").glob("*.ipynb")):
        prefix = path.name[:2]
        scenario = path.stem[3:]
        if selected and prefix not in selected:
            continue
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        started = time.monotonic()
        result = {
            "notebook": path.name,
            "source_sha256": source_hash,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "FAIL",
            "aws_scope": LIVE_SCOPE.get(SCENARIOS.get(scenario), "Não revisado"),
        }
        evidence_path = ROOT / "evidence" / f"notebook-audit-{prefix}.json"
        # Evitar que uma exceção antes da auditoria aproveite um relatório antigo.
        evidence_path.parent.mkdir(exist_ok=True)
        evidence_path.write_text(json.dumps({"status": "RUNNING"}))
        try:
            if scenario not in SCENARIOS:
                raise ValueError(f"UNREVIEWED_NOTEBOOK: {path.name}")
            notebook = nbformat.read(path, as_version=4)
            result["source_code_cells"] = sum(c.cell_type == "code" for c in notebook.cells)
            check_offline_defaults(notebook)
            first = next(i for i, c in enumerate(notebook.cells) if c.cell_type == "code")
            notebook.cells[first:first] = [
                nbformat.v4.new_markdown_cell("Instrumentação externa de auditoria local."),
                nbformat.v4.new_code_cell(
                    "from scripts.audit_notebooks import Observer\n"
                    f"_audit_observer = Observer({scenario!r}, {prefix!r}).start()"
                ),
            ]
            last = next(
                i for i, c in enumerate(notebook.cells)
                if "cleanup_cloud" in c.metadata.get("tags", [])
            )
            notebook.cells[last:last] = [
                nbformat.v4.new_markdown_cell("Comparar conteúdo e efeitos antes da limpeza."),
                nbformat.v4.new_code_cell(
                    "_audit_observer.inspect(globals())\ndel _audit_observer"
                ),
            ]
            NotebookClient(
                notebook, timeout=180, resources={"metadata": {"path": str(ROOT)}}
            ).execute(env=environment)
            observed = json.loads(evidence_path.read_text())
            if observed["status"] != "MATCH":
                raise AssertionError("INDEPENDENT_AUDIT_DID_NOT_COMPLETE")
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != source_hash:
                raise AssertionError("NOTEBOOK_CHANGED_DURING_AUDIT")
            result["cleanup_local"] = cleanup_status(notebook, "cleanup_local", "cleanup_local")
            result["cleanup_cloud"] = cleanup_status(notebook, "cleanup_cloud", "cloud_cleanup")
            if result["cleanup_local"] != "PASS" or result["cleanup_cloud"] != "NOT_RUN":
                raise AssertionError("UNEXPECTED_CLEANUP_STATUS")
            result["executed_source_code_cells"] = sum(
                c.cell_type == "code" and c.execution_count is not None for c in notebook.cells
            ) - 2
            result.update(observed)
        except Exception as exc:
            result["status"] = "FAIL"
            result["error_type"] = type(exc).__name__
            # Saídas completas permanecem apenas no kernel: não exportar tokens.
            observed = json.loads(evidence_path.read_text())
            result["checks"] = observed.get("checks", [])
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        results.append(result)
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        aggregate.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        print(
            f"{path.name}: {result['status']}; {len(result.get('checks', []))} observações",
            flush=True,
        )
    if not results or any(result["status"] != "MATCH" for result in results):
        raise SystemExit("Divergências em evidence/notebook-audit*.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebooks", nargs="+", help="IDs, por exemplo 01 14")
    run(parser.parse_args().notebooks)
