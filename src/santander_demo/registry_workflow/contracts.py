"""Contratos sintéticos compartilhados pela bancada, Runtime e IaC."""

import hashlib
import json
import re
from copy import deepcopy

TOOL = {
    "name": "consultar_risco",
    "description": "Consulta o risco sintético de C001 ou C002; não usa dados bancários reais.",
    "inputSchema": {
        "type": "object",
        "properties": {"customer_id": {"type": "string", "enum": ["C001", "C002"]}},
        "required": ["customer_id"],
        "additionalProperties": False,
    },
}
GATEWAY_TOOL = "risco___consultar_risco"
LOCAL_GATEWAY = "https://registry-workshop.invalid/mcp"
LOCAL_RUNTIME = "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/local_demo"


def risk(arguments):
    from jsonschema import validate

    validate(arguments, TOOL["inputSchema"])
    return {
        "customer_id": arguments["customer_id"],
        "risk": {"C001": "baixo", "C002": "alto"}[arguments["customer_id"]],
    }


def tool_handler(event, context):
    """Target Lambda do Gateway; o schema também é validado no backend."""
    return risk(event)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def bundle(gateway_url=LOCAL_GATEWAY, runtime_arn=LOCAL_RUNTIME, version="1.0.0"):
    """O desenvolvedor entrega metadados; não cria registros por esta função."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("VERSION_INVALID")
    if gateway_url != LOCAL_GATEWAY and not re.fullmatch(
        r"https://[a-z0-9-]+\.gateway\.bedrock-agentcore\.us-east-1\.amazonaws\.com/mcp",
        gateway_url,
    ):
        raise ValueError("GATEWAY_INVALID")
    if not re.fullmatch(
        r"arn:aws:bedrock-agentcore:us-east-1:\d{12}:runtime/[A-Za-z0-9_-]+", runtime_arn
    ):
        raise ValueError("RUNTIME_INVALID")
    mcp = {
        "name": "risco-mcp",
        "recordType": "MCP",
        "recordVersion": version,
        "description": "Servidor MCP de consulta de risco sintético para o workshop.",
        "descriptors": {
            "mcpServer": {
                "data": json.dumps(
                    {
                        "name": "workshop/risco",
                        "description": TOOL["description"],
                        "version": version,
                        "remotes": [{"type": "streamable-http", "url": gateway_url}],
                    }
                ),
                "dataSchemaVersion": "2025-12-11",
                "additionalData": {
                    "tools": {
                        "data": json.dumps({"tools": [{**TOOL, "name": GATEWAY_TOOL}]}),
                        "dataSchemaVersion": "2025-11-25",
                    }
                },
            }
        },
    }
    agent = {
        "name": "analista-risco",
        "recordType": "AGENT",
        "recordVersion": version,
        "description": "Agente determinístico que consulta risco sintético via MCP e explica o resultado.",
        # Um Runtime HTTP não é um servidor A2A. O Registry aceita custom em AGENT.
        "descriptors": {
            "custom": {
                "data": json.dumps(
                    {
                        "schema": "santander-workshop.agent/v1",
                        "protocol": "HTTP",
                        "authentication": "AWS_IAM",
                        "runtimeArn": runtime_arn,
                        "inputSchema": TOOL["inputSchema"],
                        "dependsOn": {
                            "name": mcp["name"],
                            "version": version,
                            "gatewayUrl": gateway_url,
                            "tool": GATEWAY_TOOL,
                        },
                    }
                )
            }
        },
    }
    return {"MCP": mcp, "AGENT": agent}


def validate_agent(record, *, gateway_url, runtime_arn, version):
    """Falha fechada: o catálogo descreve; configuração local define a confiança."""
    expected = bundle(gateway_url, runtime_arn, version)["AGENT"]
    if any(record.get(k) != expected[k] for k in ("recordType", "recordVersion", "descriptors")):
        raise ValueError("UNTRUSTED_AGENT_DESCRIPTOR")
    return runtime_arn


class LocalLifecycle:
    """Modelo didático de estados e papéis; não é uma implementação IAM."""

    def __init__(self):
        self.records = {}
        self.calls = 0

    def publish(self, persona, package):
        if persona != "publicador":
            raise PermissionError("PUBLISH_DENIED")
        key = package["recordType"], package["recordVersion"]
        if key in self.records:
            raise ValueError("IMMUTABLE_VERSION")
        record = {**deepcopy(package), "status": "DRAFT"}
        self.records[key] = record
        return key

    def submit(self, persona, key):
        if persona != "publicador":
            raise PermissionError("SUBMIT_DENIED")
        if self.records[key]["status"] != "DRAFT":
            raise ValueError("EXPECTED_DRAFT")
        self.records[key]["status"] = "PENDING_APPROVAL"

    def review(self, persona, key, decision, reviewed_digest):
        if persona != "aprovador":
            raise PermissionError("REVIEW_DENIED")
        record = self.records[key]
        if decision not in {"APPROVED", "REJECTED"} or record["status"] != "PENDING_APPROVAL":
            raise ValueError("INVALID_DECISION")
        if reviewed_digest != digest({k: v for k, v in record.items() if k != "status"}):
            raise ValueError("REVIEW_CHANGED")
        record["status"] = decision

    def discover(self):
        return deepcopy([r for r in self.records.values() if r["status"] == "APPROVED"])

    def execute(self, record, arguments, *, can_invoke):
        if not can_invoke:
            raise PermissionError("INVOKE_DENIED")
        if record not in self.discover():
            raise ValueError("NOT_DISCOVERABLE")
        validate_agent(
            record, gateway_url=LOCAL_GATEWAY, runtime_arn=LOCAL_RUNTIME, version="1.0.0"
        )
        result = risk(arguments)
        self.calls += 1
        return {
            "answer": f"Cliente {result['customer_id']}: risco {result['risk']}.",
            "tool": GATEWAY_TOOL,
            "result": result,
        }
