"""Tools puramente sintéticas. Não acessam bases, clientes ou o produto K2."""

import json
import logging

from jsonschema import ValidationError, validate

from santander_demo.contracts import INPUT_SCHEMA, TOOLS, DemoError


def validate_input(arguments: dict):
    try:
        validate(arguments, INPUT_SCHEMA)
    except ValidationError:
        raise DemoError("SCHEMA_INVALID") from None


def execute(tool: str, arguments: dict) -> dict:
    validate_input(arguments)
    if tool not in TOOLS:
        raise DemoError("UNKNOWN_TOOL")
    # Defesa no backend não substitui a prova de bloqueio antes da invocação.
    if arguments["max_registros"] > 50:
        raise DemoError("BACKEND_LIMIT")
    data = {
        "riscos___consultar_risco": {"rating": "B", "score": 720, "exposicao_brl": 125000},
        "fraude___consultar_fraude": {"indicios": ["dispositivo_novo"], "revisao": "manual"},
        "riscos___consultar_conhecimento_k2": {
            "documento": "K2-DEMO-001",
            "orientacao": "Revisar operações com dispositivo novo.",
            "integracao_k2": False,
        },
    }
    return {
        "cliente_id": arguments["cliente_id"],
        "synthetic": True,
        "tool": tool,
        "dados": [data[tool]],
    }


def lambda_handler(event, context):
    """O Gateway fornece o nome da tool em client_context; não vem dos argumentos."""
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    name = custom.get("bedrockAgentCoreToolName", "")
    # O target Lambda só serve Riscos/K2. Um nome de outro target não é aceito.
    if name not in {t for t in TOOLS if t.startswith("riscos___")}:
        raise DemoError("UNKNOWN_TOOL")
    result = execute(name, event)
    logging.getLogger().warning(
        json.dumps(
            {"event": "synthetic_tool_executed", "tool": name, "request_id": context.aws_request_id}
        )
    )
    return result
