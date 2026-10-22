"""Provas reais opt-in; nunca convertem indisponibilidade em um PASS."""

import json
from urllib.parse import quote
from uuid import uuid4

import httpx

from santander_demo.cloud import CloudWorkshop, gateway_session, list_tools
from santander_demo.contracts import CLIENTE, DemoError
from santander_demo.supervisor_server import USER_HEADER


def topology(config):
    accounts = {config.origin_account, config.hub_account, config.fraud_account}
    if len(accounts) != 3:
        raise DemoError("THREE_DISTINCT_ACCOUNTS_REQUIRED")
    for arn, account in [
        (config.supervisor_runtime_arn, config.origin_account),
        (config.gateway_arn, config.hub_account),
        (config.registry_arn, config.hub_account),
        (config.fraud_runtime_arn, config.fraud_account),
    ]:
        parts = arn.split(":")
        if len(parts) < 6 or parts[4] != account or parts[3] != config.region:
            raise DemoError("TOPOLOGY_ARN_MISMATCH")
    return {"mode": "AWS_CONFIG_CHECK", "distinct_accounts": 3, "execution_verified": False}


async def invoke_supervisor(config, token):
    topology(config)
    CloudWorkshop(config).verify_token(token)
    url = (
        f"https://bedrock-agentcore.{config.region}.amazonaws.com/runtimes/"
        + quote(config.supervisor_runtime_arn, safe="")
        + "/invocations?qualifier=DEFAULT"
    )
    async with httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                USER_HEADER: token,
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": uuid4().hex + uuid4().hex,
            },
            json={"cliente_id": CLIENTE},
        )
    if response.status_code != 200:
        raise DemoError(f"SUPERVISOR_HTTP_{response.status_code}")
    body = response.json()
    observed = {item["tool"] for item in body.get("results", []) if "result" in item}
    if not {"riscos___consultar_risco", "fraude___consultar_fraude"} <= observed:
        raise DemoError("MULTI_ACCOUNT_RESULT_INCOMPLETE")
    return {
        "mode": "AWS_LIVE",
        "multi_account_response": "PASS",
        "request_id": response.headers.get("x-amzn-requestid"),
        "tools": sorted(observed),
        "trace_review": "REQUIRED",
    }


async def probe_policy(config, token, tool, arguments):
    """Retorna observações. MCP_TOOL_ERROR não é automaticamente uma recusa Cedar."""
    from mcp.shared.exceptions import McpError

    cloud = CloudWorkshop(config)
    identity = cloud.verify_token(token)
    preflight = cloud.preflight()
    assert preflight["policy"] == "ENFORCE"
    result = {
        "mode": "AWS_LIVE",
        "tool": tool,
        "identity": identity.summary(),
        "backend_non_invocation": "NOT_PROVEN",
    }
    try:
        async with gateway_session(config.gateway_url, token, {config.gateway_url}) as session:
            names = {t.name for t in await list_tools(session)}
            if tool not in names:
                raise DemoError("TOOL_NOT_ADVERTISED")
            response = await session.call_tool(tool, arguments)
            if not response.isError:
                result["outcome"] = "ALLOW"
                return result
            message = " ".join(c.text for c in response.content if c.type == "text").lower()
    except McpError as exc:
        message = exc.error.message.lower()
    # Frase específica do controle de tool; 401/403 genérico não é usado.
    result["outcome"] = (
        "POLICY_DENIAL_REPORTED" if "tool call not allowed" in message else "UNCLASSIFIED_ERROR"
    )
    return result


def read_log_evidence(session, log_group, start_ms, end_ms):
    """Leitura limitada. Nunca retorna body ou headers de logs à evidência distribuída."""
    client = session.client("logs")
    events, token = [], None
    for _ in range(20):
        args = {
            "logGroupName": log_group,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 100,
        }
        if token:
            args["nextToken"] = token
        response = client.filter_log_events(**args)
        for event in response.get("events", []):
            try:
                message = json.loads(event["message"])
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            events.append(
                {
                    "event_id": event["eventId"],
                    "timestamp": event["timestamp"],
                    **{
                        key: message[key]
                        for key in ["request_id", "trace_id", "event", "tool"]
                        if key in message
                    },
                }
            )
        new_token = response.get("nextToken")
        if not new_token or new_token == token:
            return {"events": events, "complete": True}
        token = new_token
    return {"events": events, "complete": False}
