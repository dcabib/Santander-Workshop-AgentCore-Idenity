import json
import sys

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from santander_demo.cloud import list_tools, tool_json
from santander_demo.contracts import CLIENTE, DemoError
from santander_demo.databricks import DelegatedDatabricks


async def test_actual_mcp_protocol_over_stdio():
    params = StdioServerParameters(command=sys.executable, args=["-m", "santander_demo.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await list_tools(session)
            assert [t.name for t in tools] == ["consultar_fraude"]
            result = tool_json(
                await session.call_tool(
                    "consultar_fraude", {"cliente_id": CLIENTE, "max_registros": 5}
                )
            )
            # FastMCP pode envelopar dict em structuredContent como result.
            result = result.get("result", result)
            assert result["synthetic"] is True
            bad = await session.call_tool(
                "consultar_fraude", {"cliente_id": CLIENTE, "max_registros": 51}
            )
            assert bad.isError


def database(handler):
    return DelegatedDatabricks(
        "https://demo.azuredatabricks.net",
        "warehouse",
        "tester@example.invalid",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_obo_exchange_failure_never_falls_back_to_m2m():
    requests = []

    def handler(request):
        requests.append(request)
        assert b"client_secret" not in request.content
        return httpx.Response(403, json={"error": "access_denied"})

    with pytest.raises(DemoError, match="DATABRICKS_EXCHANGE_DENIED"):
        database(handler).prove("user-token", "demo.sandbox.canary", expect_grant=True)
    assert len(requests) == 1
    with pytest.raises(DemoError, match="DELEGATION_REQUIRED"):
        database(handler).exchange("")
    assert len(requests) == 1


def test_email_shaped_service_principal_does_not_prove_obo():
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "delegated"})
        return httpx.Response(
            200,
            json={
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [["service-principal@example.invalid"]]},
            },
        )

    with pytest.raises(DemoError, match="DATABRICKS_PRINCIPAL_MISMATCH"):
        database(handler).prove("user-token", "demo.sandbox.canary", expect_grant=True)


@pytest.mark.parametrize("code,passed", [("PERMISSION_DENIED", True), ("SYNTAX_ERROR", False)])
def test_source_denial_is_not_any_sql_error(code, passed):
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "delegated"})
        assert request.headers["Authorization"] == "Bearer delegated"
        statement = json.loads(request.content)["statement"]
        if statement == "SELECT current_user()":
            return httpx.Response(
                200,
                json={
                    "status": {"state": "SUCCEEDED"},
                    "result": {"data_array": [["tester@example.invalid"]]},
                },
            )
        return httpx.Response(
            200,
            json={
                "status": {"state": "FAILED", "error": {"error_code": code}},
            },
        )

    if passed:
        assert (
            database(handler).prove("user-token", "demo.sandbox.canary", expect_grant=False)[
                "grant"
            ]
            is False
        )
    else:
        with pytest.raises(DemoError, match="DATABRICKS_DENIAL_NOT_PROVEN"):
            database(handler).prove("user-token", "demo.sandbox.canary", expect_grant=False)


def test_sql_identifier_is_not_injectable():
    with pytest.raises(ValueError):
        database(lambda r: None).prove("user-token", "x; DROP TABLE y", expect_grant=True)
