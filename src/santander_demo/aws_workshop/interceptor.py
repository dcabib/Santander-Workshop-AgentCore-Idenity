"""Propagação JWT documentada para targets MCP; nenhum token entra nos logs."""

import json
import os

from .contracts import RISK, TOOLS, USER_TOKEN_HEADER
from .identity import verify


def transform(event, config, verifier=verify):
    if event.get("interceptorInputVersion") != "1.0":
        raise ValueError("UNSUPPORTED_INTERCEPTOR_VERSION")
    request = event["mcp"]["gatewayRequest"]
    body = request["body"]
    # Somente os destinos MCP declarados no IaC recebem o JWT humano.
    # initialize/tools/list usam o catálogo estático do Gateway.
    result = {"interceptorOutputVersion": "1.0", "mcp": {
        "transformedGatewayRequest": {"body": body},
    }}
    if body.get("method") != "tools/call":
        return result
    name = body.get("params", {}).get("name")
    if name == "riscos___" + RISK["name"]:
        return result  # Target Lambda recebe autenticação IAM do Gateway.
    downstream = {"especialista___" + tool["name"] for tool in TOOLS}
    federated = {
        prefix + "___" + name
        for prefix in ["retail", "transaction", "lending"]
        for name in {*downstream, "riscos___" + RISK["name"]}
    }
    if name not in downstream | federated:
        raise ValueError("UNTRUSTED_PROPAGATION_TARGET")
    values = [
        value for key, value in request.get("headers", {}).items()
        if key.lower() == "authorization"
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError("ONE_AUTHORIZATION_HEADER_REQUIRED")
    authorization = values[0]
    if (
        not authorization.startswith("Bearer ") or len(authorization) > 4096
        or any(ord(char) < 32 or ord(char) > 126 for char in authorization)
    ):
        raise ValueError("INVALID_BEARER_HEADER")
    verifier(authorization[7:], config)
    # O Runtime MCP autentica a role do Gateway com SigV4. O JWT da pessoa
    # segue em um header separado para não substituir a assinatura IAM.
    # Gateways federados continuam usando seu authorizer JWT de entrada.
    header = USER_TOKEN_HEADER if name in downstream else "Authorization"
    result["mcp"]["transformedGatewayRequest"]["headers"] = {header: authorization}
    return result


def handler(event, context):
    return transform(event, json.loads(os.environ["WORKSHOP_AUTH"]))
