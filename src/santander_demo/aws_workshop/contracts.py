"""Contratos compartilhados pelo MCP, Gateway e material didático."""

import json

USER_TOKEN_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-User-Authorization"

REQUEST = {
    "type": "string",
    "description": "UUID da execução para correlação nos logs, sem dados pessoais.",
}
TOOLS = [
    {
        "name": "consultar_fraude",
        "description": "Consulta sinais sintéticos de fraude autorizados para a pessoa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cliente_id": {"type": "string"},
                "max_registros": {"type": "integer"},
                "request_id": REQUEST,
            },
            "required": ["cliente_id", "max_registros", "request_id"],
        },
    },
    {
        "name": "consultar_tabela",
        "description": "Consulta uma tabela no simulador AWS de Databricks, com ACL na fonte.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabela": {"type": "string"},
                "request_id": REQUEST,
            },
            "required": ["tabela", "request_id"],
        },
    },
    {
        "name": "identidade_fonte",
        "description": "Identidade verificada no simulador AWS; equivalente didático a current_user().",
        "inputSchema": {
            "type": "object", "properties": {"request_id": REQUEST}, "required": ["request_id"],
        },
    },
    {
        "name": "memorizar_referencia",
        "description": "Grava somente uma referência autorizada no AgentCore Memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tabela": {"type": "string"},
                "session_id": {"type": "string"},
                "request_id": REQUEST,
            },
            "required": ["tabela", "session_id", "request_id"],
        },
    },
    {
        "name": "recuperar_memoria",
        "description": "Lê referências da própria pessoa e revalida a ACL antes de buscar conteúdo.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}, "request_id": REQUEST},
            "required": ["session_id", "request_id"],
        },
    },
]
RISK = {
    "name": "consultar_risco",
    "description": "Consulta o risco sintético por cliente, via Lambda.",
    "inputSchema": TOOLS[0]["inputSchema"],
}


def policies(gateway, issuer, supervisor, riscos, users, prefix="especialista"):
    """Claims Cognito nativas; nenhum alias oid/tid ou token gerado pelo notebook."""
    def permit(name, user_ids, clients, actions, predicates):
        principals = ", ".join(f"AgentCore::OAuthUser::{json.dumps(x)}" for x in user_ids)
        common = [
            f"[{principals}].contains(principal)",
            f'principal.hasTag("iss") && principal.getTag("iss") == {json.dumps(issuer)}',
            'principal.hasTag("token_use") && principal.getTag("token_use") == "id"',
            'principal.hasTag("aud") && '
            + json.dumps(clients) + '.contains(principal.getTag("aud"))',
        ]
        operations = ", ".join(f"AgentCore::Action::{json.dumps(x)}" for x in actions)
        return name, (
            f"permit(principal is AgentCore::OAuthUser, action in [{operations}], "
            f"resource == AgentCore::Gateway::{json.dumps(gateway)}) when {{\n  "
            + " &&\n  ".join(common + predicates) + "\n};"
        )

    limit = [
        "context.input.cliente_id == \"C001\"",
        "context.input.max_registros >= 1",
        "context.input.max_registros <= 10",
    ]
    return dict([
        permit("AllowRisk", [users["a"], users["c"]], [supervisor, riscos],
               ["riscos___consultar_risco"], limit),
        permit("AllowFraud", [users["b"], users["c"]], [supervisor],
               [prefix + "___consultar_fraude"], limit),
        permit("AllowIdentityMemory", [users[x] for x in "abc"], [supervisor, riscos],
               [prefix + "___identidade_fonte", prefix + "___recuperar_memoria"], []),
        permit("AllowRiskTables", [users[x] for x in "abc"], [supervisor, riscos],
               [prefix + "___consultar_tabela", prefix + "___memorizar_referencia"],
               ['["riscos", "k2"].contains(context.input.tabela)']),
        permit("AllowFraudTable", [users[x] for x in "bc"], [supervisor],
               [prefix + "___consultar_tabela", prefix + "___memorizar_referencia"],
               ['context.input.tabela == "fraude"']),
    ])
