"""Contratos compartilhados pelos backends, políticas, clientes e notebooks."""

from copy import deepcopy

CLIENTE = "SANT-DEMO-001"
LOCAL_GATEWAY_ARN = "arn:aws:bedrock-agentcore:us-east-1:000000000000:gateway/local-demo"
LOCAL_ENDPOINT = "https://gateway.local.invalid/mcp"
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cliente_id": {"type": "string", "enum": [CLIENTE]},
        # Sem maximum: o caso 51 deve chegar ao Cedar e demonstrar a recusa.
        "max_registros": {"type": "integer", "minimum": 1},
    },
    "required": ["cliente_id", "max_registros"],
    "additionalProperties": False,
}
TOOLS = {
    "riscos___consultar_risco": {
        "domain": "riscos",
        "description": "Consultar risco sintético de crédito do cliente de demonstração.",
    },
    "riscos___consultar_conhecimento_k2": {
        "domain": "riscos",
        "description": "Consultar referência sintética de conhecimento K2; sem integração ao K2.",
    },
    "fraude___consultar_fraude": {
        "domain": "fraude",
        "description": "Consultar indícios sintéticos de fraude do cliente de demonstração.",
    },
}


def tool_descriptors():
    return [
        {"name": name, "description": spec["description"], "inputSchema": deepcopy(INPUT_SCHEMA)}
        for name, spec in TOOLS.items()
    ]


class DemoError(Exception):
    """Erro estável sem respostas HTTP, credenciais ou dados pessoais."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
