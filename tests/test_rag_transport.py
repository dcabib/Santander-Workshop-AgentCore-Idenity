import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from botocore.exceptions import ClientError
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from santander_demo.rag import client, transport


@pytest.mark.parametrize("citation", ["R2", "F2", "R4", "F99"])
def test_model_cannot_cite_a_document_absent_from_actual_context(citation):
    model = MagicMock()
    model.converse.return_value = {
        "output": {"message": {"content": [{"text": f"Resposta [{citation}]"}]}}
    }
    with pytest.raises(ValueError, match="MODEL_CITED_UNRETRIEVED_DOCUMENT"):
        client.generate_answer(
            model, "model", "pergunta", [{"id": "R1", "domain": "riscos", "text": "fonte"}]
        )


@pytest.mark.parametrize(
    "http_status,aws_error",
    [
        (401, "AccessDeniedException"),
        (200, "AccessDeniedException"),
        (401, "ValidationException"),
    ],
)
async def test_authorization_probe_requires_actual_auth_and_iam_denials(
    monkeypatch, http_status, aws_error
):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        transport.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda request: httpx.Response(http_status, json={})),
            **kwargs,
        ),
    )
    caller = MagicMock()
    caller.client.return_value.retrieve.side_effect = ClientError(
        {"Error": {"Code": aws_error, "Message": "fixture"}}, "Retrieve"
    )
    env = {
        "GatewayUrl": "https://test.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "KnowledgeBaseId": "LOCALKB001",
    }
    if http_status == 200 or aws_error != "AccessDeniedException":
        with pytest.raises((ValueError, ClientError)):
            await transport.authorization_probe({"region": "us-east-1"}, env, caller)
    else:
        result = await transport.authorization_probe({"region": "us-east-1"}, env, caller)
        assert result["direct_retrieve_iam_denied"] is True
        assert result["gateway_http_denials"] == {"anonymous": 401, "invalid_jwt": 401}


def log_event(event_id, request_id, body):
    return {
        "eventId": event_id,
        "message": json.dumps({"request_id": request_id, "body": body}),
    }


@pytest.mark.parametrize("case,expected", [("a", "ALLOW"), ("d", "DENY"), ("spoof", "DENY")])
def test_log_correlation_requires_exact_request_tool_and_native_policy(case, expected):
    session = MagicMock()
    row = {"case": case, "gateway_request_ids": ["request-a"]}
    env = {"GatewayLogGroup": "fixture"}
    session.client.return_value.filter_log_events.return_value = {
        "events": [
            log_event("bad1", "request-b", {"tool": "rag___Retrieve"}),
            log_event("bad2", "request-a", {"tool": "other___Tool"}),
            log_event("tool", "request-a", {"tool": "rag___Retrieve"}),
        ]
    }
    transport.correlate(session, env, [row], 1000)
    assert row["gateway_log_correlation_verified"] is False
    session.client.return_value.filter_log_events.return_value["events"].append(
        log_event("decision", "request-a", {"policy": {"decision": expected}})
    )
    transport.correlate(session, env, [row], 1000)
    assert row["gateway_log_correlation_verified"] is True
    assert row["gateway_log_event_ids"] == ["decision", "tool"]
    assert row["gateway_policy_decisions"] == {"request-a": [expected]}


@pytest.mark.parametrize(
    "events",
    [
        [{"eventId": "text", "message": "request-a rag___Retrieve ALLOW"}],
        [log_event("decision", "request-b", {"policy": {"decision": "ALLOW"}})],
        [log_event("decision", "request-a", {"policy": {"decision": "DENY"}})],
        [
            log_event("allow", "request-a", {"policy": {"decision": "ALLOW"}}),
            log_event("deny", "request-a", {"policy": {"decision": "DENY"}}),
        ],
    ],
)
def test_log_correlation_rejects_unrelated_missing_or_contradictory_decisions(events):
    session = MagicMock()
    session.client.return_value.filter_log_events.return_value = {
        "events": [log_event("tool", "request-a", {"tool": "rag___Retrieve"}), *events]
    }
    row = {"case": "a", "gateway_request_ids": ["request-a"]}
    transport.correlate(session, {"GatewayLogGroup": "fixture"}, [row], 1000)
    assert row["gateway_log_correlation_verified"] is False


@pytest.mark.parametrize(
    "failure,attempts,succeeds",
    [
        (httpx.ReadError("interrupted"), 3, True),
        (ExceptionGroup("network", [httpx.ReadError("interrupted")]), 3, True),
        (McpError(ErrorData(code=-32000, message="tool call not allowed")), 1, False),
        (ExceptionGroup("mixed", [httpx.ReadError("interrupted"), ValueError("bad")]), 1, False),
        (httpx.ConnectTimeout("offline"), 3, False),
    ],
)
async def test_retrieval_retry_is_bounded_and_never_retries_policy_errors(
    monkeypatch, failure, attempts, succeeds
):
    session = MagicMock()
    result = object()
    session.call_tool = AsyncMock(
        side_effect=[failure, failure, result] if succeeds else [failure] * 3
    )
    connections = []

    @asynccontextmanager
    async def connect(url, token, allowed, **kwargs):
        connections.append((url, token, allowed))
        yield session

    monkeypatch.setattr(client, "gateway_session", connect)
    monkeypatch.setattr(client.asyncio, "sleep", AsyncMock())
    arguments = {"userContext": {"userId": "a@example.invalid"}}
    if succeeds:
        assert await client._retrieve("https://gateway", "same-token", arguments, []) is result
    else:
        with pytest.raises(type(failure)):
            await client._retrieve("https://gateway", "same-token", arguments, [])
    assert len(connections) == attempts
    assert all(x == connections[0] for x in connections)
    assert all(c.args == ("rag___Retrieve", arguments) for c in session.call_tool.call_args_list)
