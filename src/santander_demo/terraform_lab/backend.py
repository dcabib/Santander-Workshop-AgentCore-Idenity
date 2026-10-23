"""Ferramenta Lambda sem dependências externas e sem dados de clientes reais."""

import json

TOOL_NAME = "banking___get_customer_profile"
CUSTOMERS = {
    "C001": {
        "customer_id": "C001",
        "display_name": "Cliente sintético Aurora",
        "segment": "varejo",
        "balance_brl": "1250.00",
        "risk_band": "baixo",
    },
    "C002": {
        "customer_id": "C002",
        "display_name": "Cliente sintético Horizonte",
        "segment": "empresas",
        "balance_brl": "8700.00",
        "risk_band": "moderado",
    },
}


def customer_profile(customer_id):
    if not isinstance(customer_id, str) or customer_id not in CUSTOMERS:
        raise ValueError("CUSTOMER_NOT_IN_SYNTHETIC_DATASET")
    return {"data_classification": "SYNTHETIC", **CUSTOMERS[customer_id]}


def handler(event, context):
    """Gateway envia argumentos no event e metadados em client_context.custom."""
    custom = getattr(getattr(context, "client_context", None), "custom", {}) or {}
    if custom.get("bedrockAgentCoreToolName") != TOOL_NAME:
        raise ValueError("UNEXPECTED_GATEWAY_TOOL")
    if not isinstance(event, dict) or set(event) != {"customer_id"}:
        raise ValueError("INVALID_TOOL_ARGUMENTS")
    result = customer_profile(event["customer_id"])
    proof = {
        "gateway_request_id": custom.get("bedrockAgentCoreAwsRequestId"),
        "lambda_request_id": getattr(context, "aws_request_id", None),
        "tool": TOOL_NAME,
    }
    print(json.dumps({"event": "synthetic_tool_completed", **proof}))
    return {**result, "execution": proof}
