"""Evidências conservadoras: erro de rede/OAuth nunca vira prova de Policy ou grant."""

import hashlib
import json
import re


def payload(result):
    if result.structuredContent is not None:
        return result.structuredContent
    for block in result.content:
        if block.type == "text":
            try:
                value = json.loads(block.text)
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
    return {}


def classify_error(text):
    message = text.casefold()
    # A ordem evita chamar erro de troca de token de negativa do Unity Catalog.
    if any(
        s in message
        for s in (
            "token exchange",
            "invalid_token",
            "invalid_grant",
            "authorization error when sending",
        )
    ):
        return "AUTH_OR_EXCHANGE_ERROR"
    if "tool call not allowed" in message:
        return "POLICY_DENY_REPORTED"
    if any(
        s in message
        for s in (
            "insufficient_privileges",
            "insufficient_permissions",
            "permission_denied",
            "sqlstate: 42501",
            "sqlstate=42501",
        )
    ):
        return "SOURCE_GRANT_DENY_REPORTED"
    return "UNCLASSIFIED_ERROR"


def statement_evidence(result, expected_principal):
    """Compara principal exato; o formato de e-mail não é uma prova de delegação."""
    doc = payload(result)
    text = " ".join(block.text for block in result.content if block.type == "text")
    status = doc.get("status", {})
    state = status.get("state") if isinstance(status, dict) else status
    error = doc.get("error") or (status.get("error") if isinstance(status, dict) else None)
    if result.isError or error or state in {"FAILED", "CANCELED", "CLOSED"}:
        return {"outcome": classify_error(text + json.dumps(error)), "query_id": query_id(doc)}
    if state in {"PENDING", "RUNNING"}:
        return {"outcome": "QUERY_INCOMPLETE", "query_id": query_id(doc)}
    rows = (doc.get("result") or {}).get("data_array") or []
    principal = None
    if rows and isinstance(rows[0], list) and rows[0]:
        principal = rows[0][0]
    elif rows and isinstance(rows[0], dict):
        values = rows[0].get("values", [])
        principal = values[0].get("string_value") if values else None
    # Não há fallback para shared SP, JWT decodificado sem assinatura ou heurística.
    matches = (
        isinstance(principal, str)
        and bool(expected_principal)
        and principal.casefold() == expected_principal.casefold()
    )
    return {
        "outcome": "PER_USER_VERIFIED" if matches else "IDENTITY_NOT_PROVEN",
        "principal_matches": matches,
        "query_id": query_id(doc),
    }


def query_id(doc):
    value = doc.get("statement_id") or doc.get("query_id")
    return (
        value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else None
    )


def fingerprint(query):
    return hashlib.sha256(query.encode()).hexdigest()


def acceptance(rows):
    """Retorna explicitamente as provas faltantes; nunca promove simulação a integração."""
    required = {
        "a_riscos": "PER_USER_VERIFIED",
        "a_fraude": "PER_USER_VERIFIED",
        "a_wrong_agent": "POLICY_DENY_REPORTED",
        "b_sem_grant": "SOURCE_GRANT_DENY_REPORTED",
    }
    missing = []
    by_case = {row.get("case"): row for row in rows}
    for case, expected in required.items():
        row = by_case.get(case, {})
        if row.get("mode") != "AWS_LIVE" or row.get("outcome") != expected:
            missing.append(case)
        if case in {"a_riscos", "a_fraude", "b_sem_grant"} and not row.get("identity_verified"):
            missing.append(case + ":identity")
    # Resultado da tool não comprova sozinho execução em todos os saltos.
    for case in ("a_riscos", "a_fraude"):
        row = by_case.get(case, {})
        if not row.get("query_id"):
            missing.append(case + ":query_id")
        if not row.get("gateway_log_correlation_verified"):
            missing.append(case + ":gateway_logs")
    denied = by_case.get("a_wrong_agent", {})
    if not denied.get("backend_non_execution_verified"):
        missing.append("a_wrong_agent:backend_non_execution")
    a, b = by_case.get("a_riscos", {}), by_case.get("b_sem_grant", {})
    if not a.get("user_ref") or not b.get("user_ref") or a.get("user_ref") == b.get("user_ref"):
        missing.append("two_distinct_users")
    return {
        "status": "PASS" if not missing else "PENDING_EVIDENCE",
        "missing": sorted(set(missing)),
    }
