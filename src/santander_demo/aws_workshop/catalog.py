"""Descriptors de agentes HTTP: catálogo descreve, outputs IaC estabelecem confiança."""

import json
import re

from santander_demo.aws_endpoints import gateway_region


def origin_bundle(identity, gateway_url, runtimes):
    try:
        region = gateway_region(gateway_url)
    except ValueError as exc:
        raise ValueError("CATALOG_GATEWAY_INVALID") from exc
    result = {}
    for label, application, client in [
        ("Riscos", "riscos", "RiscosClientId"),
        ("Fraude", "fraude", "SupervisorClientId"),
    ]:
        arn = runtimes[label]
        if not re.fullmatch(
            rf"arn:aws:bedrock-agentcore:{region}:\d{{12}}:runtime/[A-Za-z0-9_-]+", arn,
        ):
            raise ValueError("CATALOG_RUNTIME_INVALID")
        result[label] = {
            "name": "santander-origem-" + application,
            "recordType": "AGENT", "recordVersion": "1.0.0",
            "description": (
                f"Agente de {application} no Runtime da conta de origem; consulta "
                "o simulador Databricks AWS em Transaction por meio do Gateway da plataforma."
            ),
            "descriptors": {"custom": {"data": json.dumps({
                "schema": "santander-workshop.origin-agent/v1",
                "protocol": "HTTP", "authentication": "COGNITO_JWT",
                "issuer": identity["Issuer"], "audience": identity[client],
                "runtimeArn": arn, "gatewayUrl": gateway_url,
                "sourceKind": "AWS_SIMULATED_DATABRICKS",
                "inputSchema": {
                    "type": "object", "required": ["question", "domain"],
                    "additionalProperties": False,
                    "properties": {
                        "question": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "domain": {"const": "transaction-banking"},
                    },
                },
            }, sort_keys=True)}},
        }
    return result


def validate_origin_record(record, expected):
    fields = ("name", "recordType", "recordVersion", "description", "descriptors")
    if any(record.get(key) != expected[key] for key in fields):
        raise ValueError("UNTRUSTED_ORIGIN_DESCRIPTOR")
    return json.loads(expected["descriptors"]["custom"]["data"])["runtimeArn"]
