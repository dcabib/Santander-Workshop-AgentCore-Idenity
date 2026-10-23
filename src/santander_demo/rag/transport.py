"""MCP real com IDs do serviço para correlacionar logs, sem registrar o bearer."""

import json
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from botocore.exceptions import ClientError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from santander_demo.banking.agent import checked_gateway
from santander_demo.cloud import checked_endpoint


async def authorization_probe(config, environment, caller):
    """Distingue autenticação ausente/inválida de negação IAM do retrieval direto."""
    url = checked_gateway(environment["GatewayUrl"], config["region"])
    denied = {}
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "rag-auth-probe", "version": "1"},
        },
    }
    async with httpx.AsyncClient(follow_redirects=False, timeout=30) as http:
        for label, token in [("anonymous", None), ("invalid_jwt", "invalid.token.value")]:
            headers = {"Accept": "application/json, text/event-stream"}
            if token:
                headers["Authorization"] = "Bearer " + token
            response = await http.post(url, json=body, headers=headers)
            if response.status_code not in {401, 403}:
                raise ValueError("GATEWAY_AUTH_DENIAL_NOT_PROVEN")
            denied[label] = response.status_code
    try:
        caller.client("bedrock-agent-runtime").retrieve(
            knowledgeBaseId=environment["KnowledgeBaseId"],
            retrievalQuery={"text": "políticas"},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "AccessDeniedException":
            raise
    else:
        raise ValueError("DIRECT_RETRIEVAL_BYPASS_NOT_BLOCKED")
    return {"gateway_http_denials": denied, "direct_retrieve_iam_denied": True}


@asynccontextmanager
async def gateway_session(url, token, allowed, *, request_ids=None):
    checked_endpoint(url, allowed)

    async def capture(response):
        try:
            request = json.loads(response.request.content)
        except (ValueError, RuntimeError):
            return
        value = response.headers.get("x-amzn-requestid")
        if request.get("method") == "tools/call" and value and request_ids is not None:
            if value not in request_ids:
                request_ids.append(value)

    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token},
        follow_redirects=False,
        timeout=httpx.Timeout(60, connect=15),
        event_hooks={"response": [capture]},
    ) as http:
        async with streamable_http_client(url, http_client=http, terminate_on_close=False) as (
            read,
            write,
            _,
        ):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=75)
            ) as mcp:
                await mcp.initialize()
                yield mcp


def correlate(session, environment, rows, since_ms):
    """Vincula ferramenta e decisão nativa pelo ID exato da requisição AWS."""
    logs = session.client("logs")
    for row in rows:
        ids = row.get("gateway_request_ids", []) + row.get("coverage_gateway_request_ids", [])
        found = []
        matched = set()
        decisions = {}
        expected = "DENY" if row.get("case") in {"d", "spoof"} else "ALLOW"
        for request_id in ids:
            response = logs.filter_log_events(
                logGroupName=environment["GatewayLogGroup"],
                startTime=since_ms,
                filterPattern=f'"{request_id}"',
                limit=100,
            )
            tool_seen = False
            policy_decisions = set()
            for event in response.get("events", []):
                try:
                    record = json.loads(event["message"])
                except (ValueError, TypeError):
                    continue
                if not isinstance(record, dict) or record.get("request_id") != request_id:
                    continue
                body = record.get("body", {})
                if "rag___Retrieve" in json.dumps(body):
                    tool_seen = True
                    found.append(event["eventId"])
                policy = body.get("policy", {}) if isinstance(body, dict) else {}
                if policy.get("decision") in {"ALLOW", "DENY"}:
                    policy_decisions.add(policy["decision"])
                    found.append(event["eventId"])
            decisions[request_id] = sorted(policy_decisions)
            if tool_seen and policy_decisions == {expected}:
                matched.add(request_id)
        row["gateway_log_correlation_verified"] = bool(ids) and matched == set(ids)
        row["gateway_log_event_ids"] = sorted(set(found))
        row["gateway_policy_decisions"] = decisions
    return rows
