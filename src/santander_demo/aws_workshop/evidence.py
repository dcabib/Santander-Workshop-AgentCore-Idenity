"""Correlação de decisões nativas e execução, sem copiar payloads nem tokens."""

import json


def events(logs, group, since_ms, value):
    """Paginação é obrigatória: CloudWatch pode retornar páginas vazias com cursor."""
    return [
        event
        for page in logs.get_paginator("filter_log_events").paginate(
            logGroupName=group, startTime=since_ms, filterPattern=f'"{value}"',
        )
        for event in page.get("events", [])
    ]


def backend_event(event, correlation):
    # Runtime e Lambda podem prefixar o JSON do logger com nível/timestamp.
    message = event["message"]
    start = message.find("{")
    if start < 0:
        return False
    try:
        record, _ = json.JSONDecoder().raw_decode(message[start:])
    except (ValueError, TypeError):
        return False
    return (
        isinstance(record, dict) and record.get("event") == "backend_invoked"
        and record.get("request_id") == correlation
    )


def correlate_policy(lab, rows, since_ms):
    """Leitura repetível; o notebook aguarda os controles ALLOW antes do aceite."""
    logs = lab.aws.client("logs")
    for row in rows:
        evidence = row["evidence"]
        ids = evidence["gateway_request_ids"]
        decisions, event_ids = {}, set()
        tools_seen = set()
        for native_id in ids:
            observed = set()
            for event in events(logs, lab.gateway["GatewayLogGroup"], since_ms, native_id):
                try:
                    record = json.loads(event["message"])
                except (ValueError, TypeError):
                    continue
                if not isinstance(record, dict) or record.get("request_id") != native_id:
                    continue
                body = record.get("body", {})
                if not isinstance(body, dict):
                    continue
                if row["tool"] in json.dumps(body):
                    tools_seen.add(native_id)
                    event_ids.add(event["eventId"])
                decision = body.get("policy", {}).get("decision")
                if decision in {"ALLOW", "DENY"}:
                    observed.add(decision)
                    event_ids.add(event["eventId"])
            decisions[native_id] = sorted(observed)
        group = (
            lab.gateway["RiskLogGroup"] if row["tool"] == "riscos___consultar_risco"
            else lab.backend["RuntimeLogGroup"]
        )
        backend = [
            event["eventId"]
            for event in events(logs, group, since_ms, evidence["request_id"])
            if backend_event(event, evidence["request_id"])
        ]
        row["correlation"] = {
            "native_policy_verified": bool(ids) and tools_seen == set(ids)
            and all(value == [row["expected"]] for value in decisions.values()),
            "decisions": decisions,
            "gateway_log_event_ids": sorted(event_ids),
            "backend_log_event_ids": sorted(set(backend)),
            "backend_observed": bool(backend),
        }
        if row["expected"] == "DENY" and backend:
            raise AssertionError("POLICY_DENIAL_EXECUTED_BACKEND")
    return rows
