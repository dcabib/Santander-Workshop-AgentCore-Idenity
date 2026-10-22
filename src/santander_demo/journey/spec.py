"""Um contrato para o Cedar local, o IaC e os agentes hospedados."""

import json
import re

import cedarpy

ACCOUNTS = ("origin", "platform", "data")
AGENTS = ("riscos", "fraude")
SCOPE = "access_as_user"
IDENTITY_QUERY = "SELECT current_user() AS principal"
SQL_SCHEMA = {
    "name": "execute_sql",
    "description": "Execute only the identity probe or the approved read-only canary query.",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}
AGENT_SCHEMA = {
    "name": "consultar",
    "description": "Consultar uma capacidade aprovada, preservando o usuário até a fonte.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "capacidade": {"type": "string", "enum": list(AGENTS)},
            "request_id": {"type": "string"},
        },
        "required": ["capacidade", "request_id"],
        "additionalProperties": False,
    },
}


def canary_query(table):
    """Não aceita SQL livre, identificadores escapados ou filtros fornecidos pelo usuário."""
    if not re.fullmatch(r"[A-Za-z_]\w*\.[A-Za-z_]\w*\.[A-Za-z_]\w*", table, re.ASCII):
        raise ValueError("CANARY_TABLE_MUST_BE_CATALOG_SCHEMA_TABLE")
    # COUNT devolve uma linha mesmo com tabela vazia; dados do cliente não saem da fonte.
    return f"SELECT current_user() AS principal, COUNT(*) AS total FROM {table}"


def tool_name(capability, account="platform"):
    if capability not in AGENTS or account not in {"platform", "data"}:
        raise ValueError("UNKNOWN_CAPABILITY")
    return ("dados___" if account == "platform" else "") + capability + "___execute_sql"


def cedar(account, gateway, tenant, callers, users, tables):
    """Policy por fronteira; a identidade do agente é azp validado no hub.

    O destino vê azp do hub. Não trata argumentos de tool como identidade.
    No DBSQL, a igualdade da query impede usar a tool de Riscos para consultar Fraude.
    """
    q = json.dumps
    policies = {}
    for capability in AGENTS:
        action = (
            capability + "___consultar" if account == "origin" else tool_name(capability, account)
        )
        caller = callers[capability] if account == "platform" else callers[account]
        sql_guard = ""
        if account != "origin":
            queries = [IDENTITY_QUERY, canary_query(tables[capability])]
            sql_guard = f" &&\n  {q(queries)}.contains(context.input.query)"
        policies[capability.title() + "Delegated"] = f"""permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::{q(action)},
  resource == AgentCore::Gateway::{q(gateway)}
)
when {{
  principal.hasTag("tid") && principal.getTag("tid") == {q(tenant)} &&
  principal.hasTag("azp") && principal.getTag("azp") == {q(caller)} &&
  principal.hasTag("oid") && {q(users)}.contains(principal.getTag("oid")) &&
  principal.hasTag("ver") && principal.getTag("ver") == "2.0" &&
  principal.hasTag("scp") && principal.getTag("scp") == {q(SCOPE)}{sql_guard}
}};"""
    return policies


def evaluate(account, claims, action, arguments, *, callers, users, tables):
    principal = {"type": "AgentCore::OAuthUser", "id": claims.get("sub", "missing")}
    decision = cedarpy.is_authorized(
        {
            "principal": principal,
            "action": {"type": "AgentCore::Action", "id": action},
            "resource": {"type": "AgentCore::Gateway", "id": "local:" + account},
            "context": {"input": arguments},
        },
        "\n".join(
            cedar(account, "local:" + account, "tenant-demo", callers, users, tables).values()
        ),
        [{"uid": principal, "attrs": {}, "parents": [], "tags": claims}],
    )
    return decision.allowed


def local_matrix():
    """Executa Cedar; as negativas da fonte só podem ser comprovadas no ensaio real."""
    callers = {"origin": "login", "riscos": "agent-riscos", "fraude": "agent-fraude", "data": "hub"}
    tables = {"riscos": "demo.riscos.canario", "fraude": "demo.fraude.canario"}
    base = {"sub": "local", "tid": "tenant-demo", "oid": "user-a", "ver": "2.0", "scp": SCOPE}
    cases = [
        ("riscos lê riscos", "platform", "agent-riscos", "riscos", "user-a", None, True),
        (
            "mesmo usuário; fraude tenta riscos",
            "platform",
            "agent-fraude",
            "riscos",
            "user-a",
            None,
            False,
        ),
        ("riscos tenta fraude", "platform", "agent-riscos", "fraude", "user-a", None, False),
        ("fraude lê fraude", "platform", "agent-fraude", "fraude", "user-a", None, True),
        (
            "usuário B passa Policy; grant decidido na fonte",
            "platform",
            "agent-riscos",
            "riscos",
            "user-b",
            None,
            True,
        ),
        ("usuário não autorizado", "data", "hub", "riscos", "user-c", None, False),
        ("destino recusa caller direto", "data", "agent-riscos", "riscos", "user-a", None, False),
        (
            "SQL de fraude pela tool riscos",
            "platform",
            "agent-riscos",
            "riscos",
            "user-a",
            canary_query(tables["fraude"]),
            False,
        ),
    ]
    rows = []
    for name, account, caller, capability, user, query, expected in cases:
        allowed = evaluate(
            account,
            {**base, "azp": caller, "oid": user},
            tool_name(capability, account),
            {"query": query or canary_query(tables[capability])},
            callers=callers,
            users=["user-a", "user-b"],
            tables=tables,
        )
        if allowed != expected:
            raise AssertionError(name)
        rows.append({"case": name, "boundary": account, "decision": "ALLOW" if allowed else "DENY"})
    return {"mode": "LOCAL_CEDAR_ONLY", "aws_oauth_databricks": "NOT_RUN", "cases": rows}
