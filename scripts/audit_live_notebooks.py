"""Executa notebooks AWS existentes e confere dados, contexto e logs do serviço.

Não provisiona recursos. RAG: instrumentação apenas em memória, sem substituir
respostas. Terraform: kernel completo seguido de leitura independente dos logs.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from unittest.mock import patch

import boto3
import nbformat
from nbclient import NotebookClient

from scripts.audit_notebooks import RAG_DOCUMENTS, ROOT
from scripts.verify_notebooks import check_offline_defaults, cleanup_status


def normalized(text):
    return " ".join(text.split())


class RagObserver:
    def __init__(self):
        self.retrievals = []
        self.generations = []
        self.workload_tokens = []
        self.checks = []

    def start(self):
        from botocore.client import BaseClient

        from santander_demo.rag import client

        actual_api = BaseClient._make_api_call
        actual_retrieve = client._retrieve

        def api_call(instance, operation, params):
            response = actual_api(instance, operation, params)
            if operation == "Converse":
                self.generations.append((params, response))
            elif operation == "GetWorkloadAccessTokenForJWT":
                self.workload_tokens.append({
                    "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
                    "issued": bool(response.get("workloadAccessToken")),
                })
            return response

        async def retrieve(url, token, arguments, request_ids, **kwargs):
            row = {"arguments": arguments, "request_ids": request_ids, "body": None}
            self.retrievals.append(row)
            result = await actual_retrieve(url, token, arguments, request_ids, **kwargs)
            row["body"] = client.payload(result) if not result.isError else None
            return result

        self.api_patch = patch.object(BaseClient, "_make_api_call", api_call)
        self.retrieve_patch = patch.object(client, "_retrieve", retrieve)
        self.api_patch.start()
        self.retrieve_patch.start()
        return self

    def check(self, name, passed, observed):
        self.checks.append({"requirement": name, "matches": bool(passed), "observed": observed})

    def inspect(self, ns):
        config, environment = ns["config"], ns["environment"]
        session = boto3.Session(profile_name=config["profile"], region_name=config["region"])
        s3 = session.client("s3")
        users = {v["email"]: k for k, v in config["users"].items()}
        sources = {}
        bucket = environment["SourceBucket"]
        for doc_id, domain in [("R1", "riscos"), ("R2", "riscos"), ("F1", "fraude"), ("F2", "fraude")]:
            key = f"documents/{domain}/{doc_id}.txt"
            text = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
            sidecar = json.loads(s3.get_object(Bucket=bucket, Key=key + ".metadata.json")["Body"].read())
            actual_acl = {users[r["Name"]]: r["Access"] for r in sidecar["accessControlList"]}
            expected_acl = {k: "ALLOW" if doc_id in v else "DENY" for k, v in RAG_DOCUMENTS.items()}
            self.check("ACL real no S3: " + doc_id, actual_acl == expected_acl, actual_acl)
            sources[doc_id] = text
        global_acl = json.loads(s3.get_object(Bucket=bucket, Key="acl/global-acl.json")["Body"].read())
        actual_global = {
            r["keyPrefix"].rstrip("/").split("/")[-1]:
                {users[e["Name"]]: e["Access"] for e in r["aclEntries"]}
            for r in global_acl
        }
        self.check("ACL global real concorda com Riscos A/C e Fraude B/C", actual_global == {
            "riscos": {"a": "ALLOW", "b": "DENY", "c": "ALLOW", "d": "DENY"},
            "fraude": {"a": "DENY", "b": "ALLOW", "c": "ALLOW", "d": "DENY"},
        }, actual_global)
        returned = {k: set() for k in "abcd"}
        chunks_verified = 0
        for row in self.retrievals:
            label = users[row["arguments"]["userContext"]["userId"]]
            if row["body"] is None:
                continue
            chunks = row["body"]["retrievalResults"]
            for chunk in chunks:
                doc_id = chunk["metadata"]["document_id"]
                text = chunk["content"]["text"]
                matches = doc_id in RAG_DOCUMENTS[label] and normalized(text) == normalized(sources[doc_id])
                self.check("Trecho bruto da KB coincide com fonte autorizada", matches,
                           {"user": label, "document_id": doc_id, "source_matches": matches})
                returned[label].add(doc_id)
                chunks_verified += 1
        observed_docs = {k: sorted(v) for k, v in returned.items()}
        self.check("Cobertura real sem usar allowed_documents()", observed_docs == RAG_DOCUMENTS, observed_docs)
        self.check("17 chamadas MCP: 15 leituras e duas negativas", len(self.retrievals) == 17,
                   {"calls": len(self.retrievals), "source_chunks_checked": chunks_verified})
        self.check("Somente três chamadas reais ao modelo", len(self.generations) == 3, len(self.generations))
        for label, (params, response) in zip("abc", self.generations, strict=True):
            chunks = json.loads(params["messages"][0]["content"][0]["text"])["trechos_autorizados"]
            ids = {c["id"] for c in chunks}
            answer = "\n".join(b["text"] for b in response["output"]["message"]["content"] if "text" in b)
            citations = set(re.findall(r"\[([RF]\d+)\]", answer))
            source_matches = all(normalized(c["text"]) == normalized(sources[c["id"]]) for c in chunks)
            # Verifica marcadores sintéticos e citações, não apenas texto não vazio.
            codes = set(re.findall(r"(?:RISCO|FRAUDE)-[A-ZÊ]+-\d+", answer))
            source_codes = set(re.findall(r"(?:RISCO|FRAUDE)-[A-ZÊ]+-\d+", " ".join(sources[i] for i in ids)))
            self.check("Contexto e resposta efetivos do modelo: " + label.upper(),
                       bool(ids) and ids <= set(RAG_DOCUMENTS[label]) and source_matches
                       and bool(citations) and citations <= ids and bool(codes)
                       and codes <= source_codes and bool(response["ResponseMetadata"]["RequestId"]),
                       {"context_ids": sorted(ids), "citations": sorted(citations),
                        "codes": sorted(codes), "source_matches": source_matches,
                        "model_request_id": response["ResponseMetadata"]["RequestId"],
                        "usage": response.get("usage")})
        self.check("Quatro WAT emitidos pelo serviço Identity",
                   len(self.workload_tokens) == 4 and all(r["issued"] and r["request_id"] for r in self.workload_tokens),
                   self.workload_tokens)
        logs = session.client("logs")
        for row in ns["live_rows"]:
            expected = "DENY" if row["case"] in {"d", "spoof"} else "ALLOW"
            request_ids = row["gateway_request_ids"] + row.get("coverage_gateway_request_ids", [])
            for request_id in request_ids:
                events = logs.filter_log_events(
                    logGroupName=environment["GatewayLogGroup"], startTime=ns["started"],
                    filterPattern=f'"{request_id}"', limit=100,
                )["events"]
                records = []
                for event in events:
                    try:
                        record = json.loads(event["message"])
                    except ValueError:
                        continue
                    if isinstance(record, dict) and record.get("request_id") == request_id:
                        records.append(record)
                decisions = {
                    r["body"]["policy"]["decision"] for r in records
                    if isinstance(r.get("body"), dict) and isinstance(r["body"].get("policy"), dict)
                }
                tool_seen = any("rag___Retrieve" in json.dumps(r.get("body")) for r in records)
                self.check("Decisão nativa do Policy vinculada à requisição",
                           decisions == {expected} and tool_seen,
                           {"case": row["case"], "request_id": request_id,
                            "decisions": sorted(decisions), "expected": expected, "tool_seen": tool_seen})
        path = ROOT / "evidence/notebook-live-audit-rag-observations.json"
        path.write_text(json.dumps(self.checks, ensure_ascii=False, indent=2) + "\n")
        self.api_patch.stop()
        self.retrieve_patch.stop()
        assert all(c["matches"] for c in self.checks), "LIVE_RAG_OBSERVATIONS_MISMATCH"


def rag():
    path, = (ROOT / "notebooks").glob("*_rag_managed_identity_policy.ipynb")
    notebook = nbformat.read(path, as_version=4)
    check_offline_defaults(notebook)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.source = cell.source.replace("RUN_AWS = False", "RUN_AWS = True")
    first = next(i for i, c in enumerate(notebook.cells) if c.cell_type == "code")
    notebook.cells[first:first] = [
        nbformat.v4.new_markdown_cell("Observar APIs reais sem substituir resultados."),
        nbformat.v4.new_code_cell("from scripts.audit_live_notebooks import RagObserver\n_live_audit = RagObserver().start()"),
    ]
    last = next(i for i, c in enumerate(notebook.cells) if "cleanup_cloud" in c.metadata.get("tags", []))
    notebook.cells[last:last] = [
        nbformat.v4.new_markdown_cell("Conferir fonte S3, contexto enviado ao modelo e decisão nativa."),
        nbformat.v4.new_code_cell("_live_audit.inspect(globals())\ndel _live_audit"),
    ]
    report = {"notebook": path.name, "started_at": datetime.now(UTC).isoformat(),
              "source_sha256": source_hash, "status": "RUNNING", "mode": "AWS_LIVE",
              "resource_mutations": "DISABLED"}
    out = ROOT / "evidence/notebook-live-audit-rag.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    try:
        NotebookClient(notebook, timeout=300, resources={"metadata": {"path": str(ROOT)}}).execute(
            env=dict(os.environ, AWS_EC2_METADATA_DISABLED="true"))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source_hash
        assert cleanup_status(notebook, "cleanup_local", "cleanup_local") == "PASS"
        assert cleanup_status(notebook, "cleanup_cloud", "cloud_cleanup") == "NOT_RUN"
        report["status"] = "MATCH"
    except Exception as exc:
        report.update(status="FAIL", error_type=type(exc).__name__)
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report["executed_code_cells"] = sum(c.cell_type == "code" and c.execution_count is not None for c in notebook.cells)
        out.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


def terraform():
    subprocess.run([sys.executable, str(ROOT / "scripts/terraform_notebook_check.py"), "--live"],
                   check=True, cwd=ROOT)
    from scripts.terraform_deploy import load_config, outputs

    config = load_config(ROOT / "config/local.terraform.json")
    environment = outputs(config)
    session = boto3.Session(profile_name=config["profile"], region_name=config["region"])
    report = json.loads((ROOT / "evidence/terraform-agentcore-live.json").read_text())
    kernel_report = json.loads((ROOT / "evidence/terraform-notebook-aws.json").read_text())
    since = int(datetime.fromisoformat(kernel_report["started_at"]).timestamp() * 1000)
    checks = []
    for name in ("runtime_anonymous_denied", "gateway_anonymous_denied",
                 "gateway_invalid_token_denied", "gateway_wrong_client_denied"):
        status = report["checks"][name]["http_status"]
        checks.append({"requirement": name + ": status HTTP observado",
                       "matches": status in {401, 403}, "observed": status})
    tools = report["checks"]["identity_to_gateway_mcp"]["tools"]
    checks.append({"requirement": "Catálogo MCP real da trilha",
                   "matches": tools == ["banking___get_customer_profile"], "observed": tools})
    error = report["checks"]["unknown_customer_error_observed"]
    checks.append({"requirement": "C999 permanece erro sem causa comprovada",
                   "matches": error["scope"] == "ERROR_WITHOUT_PROFILE"
                   and error["cause"] == "NOT_PROVEN", "observed": error})
    for key, customer, balance, risk in [
        ("runtime_C001", "C001", "1250.00", "baixo"),
        ("runtime_C002", "C002", "8700.00", "moderado"),
        ("runtime_llm", "C001", "1250.00", "baixo"),
    ]:
        result = report["checks"][key]["result"]
        for record in result["records"]:
            expected = {"customer_id": customer, "balance_brl": balance, "risk_band": risk,
                        "data_classification": "SYNTHETIC"}
            checks.append({"requirement": key + ": dados literais previstos",
                           "matches": all(record[k] == v for k, v in expected.items()), "observed": record})
            proof = record["execution"]
            events = session.client("logs").filter_log_events(
                logGroupName=environment["lambda_log_group"], startTime=since,
                filterPattern=f'"{proof["lambda_request_id"]}"', limit=100,
            )["events"]
            matches = []
            for event in events:
                try:
                    body = json.loads(event["message"])
                except ValueError:
                    continue
                if body.get("event") == "synthetic_tool_completed" and all(body.get(k) == v for k, v in proof.items()):
                    matches.append(event["eventId"])
            checks.append({"requirement": key + ": IDs provam execução Lambda em CloudWatch",
                           "matches": bool(matches), "observed": {"execution": proof, "log_events": matches}})
        if key == "runtime_llm":
            answer = result["answer"]
            checks.append({"requirement": "Resposta do agente usa cliente, saldo e risco retornados",
                           "matches": customer in answer and risk in answer.lower()
                           and any(v in answer for v in ["1250.00", "1250,00", "1.250,00", "1,250.00"]),
                           "observed": answer})
    path = ROOT / "notebooks/09_terraform_runtime_gateway_identity.ipynb"
    checks.append({"requirement": "Fonte testada não mudou",
                   "matches": hashlib.sha256(path.read_bytes()).hexdigest() == kernel_report["source_sha256"]})
    out = {"notebook": path.name, "mode": "AWS_LIVE", "checks": checks,
           "source_sha256": kernel_report["source_sha256"],
           "tested_at": datetime.now(UTC).isoformat(),
           "status": "MATCH" if all(c["matches"] for c in checks) else "MISMATCH"}
    (ROOT / "evidence/notebook-live-audit-terraform.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    assert out["status"] == "MATCH"


def registry():
    """Audita consumo e permissões do ambiente aprovado; não repete transições."""
    from botocore.client import BaseClient
    from botocore.exceptions import ClientError

    from santander_demo.registry_workflow.client import RegistryLab

    config = json.loads((ROOT / "config/local.registry.json").read_text())
    observed = []
    original = BaseClient._make_api_call

    def capture(instance, operation, params):
        try:
            response = original(instance, operation, params)
        except ClientError as exc:
            if operation == "InvokeAgentRuntime":
                observed.append({"operation": operation, "error": exc.response["Error"]["Code"],
                                 "request_id": exc.response.get("ResponseMetadata", {}).get("RequestId")})
            raise
        row = {"operation": operation,
               "request_id": response.get("ResponseMetadata", {}).get("RequestId")}
        if operation == "GetRegistryRecord":
            row["record_status"] = response["status"]
        if operation == "SimulatePrincipalPolicy":
            row["decisions"] = [r["EvalDecision"] for r in response["EvaluationResults"]]
        if operation in {"GetRegistryRecord", "InvokeAgentRuntime", "SimulatePrincipalPolicy"}:
            observed.append(row)
        return response

    with patch.object(BaseClient, "_make_api_call", capture):
        result = RegistryLab(config).acceptance()
    invocations = [r for r in observed if r["operation"] == "InvokeAgentRuntime"]
    states = [r["record_status"] for r in observed if r["operation"] == "GetRegistryRecord"]
    decisions = [r["decisions"][0] == "allowed" for r in observed if r["operation"] == "SimulatePrincipalPolicy"]
    checks = [
        {"requirement": "MCP e AGENT aprovados no serviço", "matches": states == ["APPROVED"] * 2,
         "observed": states},
        {"requirement": "Dados e resposta reais de C001",
         "matches": result["result"]["result"] == {"customer_id": "C001", "risk": "baixo"}
         and result["result"]["answer"] == "Cliente C001: risco baixo.",
         "observed": result["result"]},
        {"requirement": "Invocação assinada completa e duas negativas do Runtime",
         "matches": len(invocations) == 3 and sum("error" not in r for r in invocations) == 1
         and all(r.get("request_id") for r in invocations)
         and all(r.get("error") == "AccessDeniedException" for r in invocations if "error" in r),
         "observed": invocations},
        {"requirement": "16 decisões IAM por persona correspondem à tabela",
         "matches": decisions == [
             False, False, False, True, True, False, False, False,
             False, True, False, False, False, False, True, True,
         ], "observed": decisions},
    ]
    path = ROOT / "notebooks/07_registry_personas.ipynb"
    report = {
        "notebook": path.name, "tested_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "status": "MATCH" if all(r["matches"] for r in checks) else "MISMATCH",
        "scope": "AWS_CONSUMPTION_AND_IAM_SIMULATION",
        "not_replayed": ["DRAFT → PENDING_APPROVAL → APPROVED", "IaC publication/approval"],
        "limitations": ["Sem ID de execução Lambda no payload deste cenário",
                        "Simulação IAM não é tentativa real de escrita com papel indevido"],
        "checks": checks,
    }
    (ROOT / "evidence/notebook-live-audit-registry.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert report["status"] == "MATCH"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lab", choices=["rag", "terraform", "registry"])
    args = parser.parse_args()
    destination = ROOT / "evidence" / f"notebook-live-audit-{args.lab}.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps({"status": "RUNNING", "started_at": datetime.now(UTC).isoformat()}))
    try:
        {"rag": rag, "terraform": terraform, "registry": registry}[args.lab]()
    except Exception as exc:
        last = json.loads(destination.read_text())
        if last["status"] == "RUNNING":
            last.update(status="FAIL", error_type=type(exc).__name__)
            destination.write_text(json.dumps(last, indent=2) + "\n")
        raise
