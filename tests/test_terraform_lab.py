import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from santander_demo.terraform_lab import runtime
from santander_demo.terraform_lab.backend import TOOL_NAME, customer_profile, handler
from santander_demo.terraform_lab.client import require_denial

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "region": "us-east-1",
    "gateway_url": "https://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
    "workload_name": "demo-workload",
    "provider_name": "demo-provider",
    "scope": "demo/tools.read",
    "model_id": "amazon.nova-lite-v1:0",
}
TOOL = Tool(
    name=TOOL_NAME,
    description="Synthetic banking lookup",
    inputSchema={
        "type": "object",
        "properties": {"customer_id": {"type": "string"}},
        "required": ["customer_id"],
    },
)


def lambda_context(tool=TOOL_NAME):
    return SimpleNamespace(
        aws_request_id="lambda-request",
        client_context=SimpleNamespace(custom={
            "bedrockAgentCoreToolName": tool,
            "bedrockAgentCoreAwsRequestId": "gateway-request",
        }),
    )


def test_backend_preserves_money_and_real_execution_ids():
    result = handler({"customer_id": "C001"}, lambda_context())
    assert result["balance_brl"] == "1250.00"
    assert result["data_classification"] == "SYNTHETIC"
    assert result["execution"]["gateway_request_id"] == "gateway-request"
    result["balance_brl"] = "0"
    assert customer_profile("C001")["balance_brl"] == "1250.00"


@pytest.mark.parametrize("event,context", [
    ({"customer_id": "C999"}, lambda_context()),
    ({"customer_id": "C001", "sql": "SELECT *"}, lambda_context()),
    ({"customer_id": "C001"}, lambda_context("banking___transfer_money")),
    ({"customer_id": "C001"}, SimpleNamespace()),
])
def test_backend_rejects_unsupported_data_and_context(event, context):
    with pytest.raises(ValueError):
        handler(event, context)


def test_identity_exchanges_workload_token_for_scoped_m2m_token():
    identity = MagicMock()
    identity.get_workload_access_token.return_value = {"workloadAccessToken": "wat"}
    identity.get_resource_oauth2_token.return_value = {"accessToken": "oauth"}
    assert runtime.gateway_access_token(identity, CONFIG) == "oauth"
    identity.get_workload_access_token.assert_called_once_with(workloadName="demo-workload")
    identity.get_resource_oauth2_token.assert_called_once_with(
        workloadIdentityToken="wat",
        resourceCredentialProviderName="demo-provider",
        scopes=["demo/tools.read"],
        oauth2Flow="M2M",
    )


def test_identity_no_token_fails_closed():
    identity = MagicMock()
    identity.get_workload_access_token.return_value = {"workloadAccessToken": "wat"}
    identity.get_resource_oauth2_token.return_value = {"authorizationUrl": "https://idp.test"}
    with pytest.raises(RuntimeError, match="IDENTITY_DID_NOT_RETURN"):
        runtime.gateway_access_token(identity, CONFIG)


@pytest.mark.parametrize("url", [
    "http://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
    "https://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com.attacker.test/mcp",
    "https://attacker.test/mcp",
    CONFIG["gateway_url"] + "?redirect=https://attacker.test",
    CONFIG["gateway_url"].replace("demo.", "user:password@demo."),
    CONFIG["gateway_url"].replace("us-east-1", "us-west-2"),
])
def test_bearer_destination_is_restricted(url):
    with pytest.raises(ValueError, match="INVALID_GATEWAY"):
        runtime.validate_gateway(url, CONFIG["region"])


def tool_result(customer="C001"):
    return CallToolResult(content=[TextContent(
        type="text", text=json.dumps(handler({"customer_id": customer}, lambda_context()))
    )])


@pytest.mark.asyncio
async def test_real_mcp_client_performs_initialize_list_and_call(monkeypatch):
    """Protocolo MCP real sobre transporte HTTP em memória; não é prova AWS."""
    calls = []

    async def respond(request):
        assert request.headers["authorization"] == "Bearer ephemeral-test-token"
        if request.method == "GET":
            return httpx.Response(405)
        body = json.loads(request.content)
        calls.append(body["method"])
        if "id" not in body:
            return httpx.Response(202)
        results = {
            "initialize": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock-gateway", "version": "1"},
            },
            "tools/list": {"tools": [TOOL.model_dump(by_alias=True, exclude_none=True)]},
            "tools/call": tool_result().model_dump(by_alias=True, exclude_none=True),
        }
        if body["method"] == "tools/call":
            assert body["params"]["name"] == TOOL_NAME
            assert body["params"]["arguments"] == {"customer_id": "C001"}
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"], "result": results[body["method"]],
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr(runtime.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(respond), **kwargs
    ))
    async with runtime.connect_gateway(CONFIG["gateway_url"], "ephemeral-test-token") as mcp:
        assert [t.name for t in await runtime.list_tools(mcp)] == [TOOL_NAME]
        assert (await runtime.call_profile(mcp, "C001"))["balance_brl"] == "1250.00"
    assert calls == ["initialize", "notifications/initialized", "tools/list", "tools/call"]


class FakeMCP:
    def __init__(self, *, error=False):
        self.error = error

    async def list_tools(self, cursor=None):
        return ListToolsResult(tools=[TOOL])

    async def call_tool(self, name, arguments):
        assert name == TOOL_NAME
        if self.error:
            return CallToolResult(isError=True, content=[TextContent(type="text", text="failed")])
        return tool_result(arguments["customer_id"])


@pytest.mark.asyncio
async def test_runtime_orchestration_and_no_token_in_return():
    @asynccontextmanager
    async def connector(url, token):
        assert (url, token) == (CONFIG["gateway_url"], "SECRET-OAUTH-TOKEN")
        yield FakeMCP()

    session = MagicMock()
    session.client().get_workload_access_token.return_value = {"workloadAccessToken": "wat"}
    session.client().get_resource_oauth2_token.return_value = {"accessToken": "SECRET-OAUTH-TOKEN"}
    result = await runtime.run(
        {"customer_id": "C002"}, CONFIG, session=session, connector=connector
    )
    assert result["records"][0]["balance_brl"] == "8700.00"
    assert result["tool_calls"] == [TOOL_NAME]
    assert "SECRET-OAUTH-TOKEN" not in json.dumps(result)


@pytest.mark.asyncio
async def test_tool_failure_is_never_replaced_with_synthetic_success():
    with pytest.raises(RuntimeError, match="GATEWAY_TOOL_RETURNED_ERROR"):
        await runtime.call_profile(FakeMCP(error=True), "C001")


@pytest.mark.asyncio
async def test_model_must_call_tool_before_answering():
    bedrock = MagicMock()
    bedrock.converse.side_effect = [
        {"stopReason": "tool_use", "output": {"message": {
            "role": "assistant",
            "content": [{"toolUse": {
                "toolUseId": "t1", "name": TOOL_NAME, "input": {"customer_id": "C001"},
            }}],
        }}},
        {"stopReason": "end_turn", "output": {"message": {
            "role": "assistant", "content": [{"text": "Saldo sintético de R$ 1.250,00."}],
        }}},
    ]
    result = await runtime.converse_agent(FakeMCP(), [TOOL], bedrock, "model", "C001")
    assert result["tool_calls"] == [TOOL_NAME]
    assert result["records"][0]["balance_brl"] == "1250.00"
    assert bedrock.converse.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    [{"text": "Resposta inventada sem consulta."}],
    [{"toolUse": {
        "toolUseId": "t1", "name": TOOL_NAME, "input": {"customer_id": "C002"},
    }}],
])
async def test_model_cannot_skip_lookup_or_change_customer(content):
    bedrock = MagicMock()
    bedrock.converse.return_value = {
        "stopReason": "end_turn",
        "output": {"message": {"role": "assistant", "content": content}},
    }
    with pytest.raises(RuntimeError):
        await runtime.converse_agent(FakeMCP(), [TOOL], bedrock, "model", "C001")


@pytest.mark.parametrize("response", [
    httpx.Response(200, headers={"x-amzn-requestid": "id"}),
    httpx.Response(403),
    httpx.Response(404, headers={"x-amzn-requestid": "id"}),
])
def test_cloud_denial_evidence_does_not_accept_success_or_unknown_proxy(response):
    with pytest.raises(AssertionError):
        require_denial(response)


def test_cloud_denial_accepts_service_auth_error():
    assert require_denial(httpx.Response(
        403, headers={"x-amzn-errortype": "AccessDeniedException"}
    )) == {"status": "PASS", "http_status": 403}


def test_generic_tool_error_does_not_prove_unknown_customer_or_permission_denial():
    from mcp.types import CallToolResult, TextContent

    from santander_demo.terraform_lab.client import observe_unknown_customer_error

    result = CallToolResult(
        isError=True, content=[TextContent(type="text", text="An internal error occurred.")]
    )
    observed = observe_unknown_customer_error(result)
    assert observed["scope"] == "ERROR_WITHOUT_PROFILE"
    assert observed["cause"] == "NOT_PROVEN"
    assert observed["error_category"] == "GATEWAY_INTERNAL_ERROR"
    result.structuredContent = {"balance_brl": "1250.00"}
    with pytest.raises(AssertionError, match="ERROR_WITHOUT_PROFILE"):
        observe_unknown_customer_error(result)


def test_deploy_clears_ambient_credentials_and_does_not_mutate_with_sdk():
    from scripts.terraform_deploy import environment

    config = {"profile": "sandbox", "region": "us-east-1"}
    env = environment(config)
    assert env["AWS_PROFILE"] == "sandbox"
    assert "AWS_ACCESS_KEY_ID" not in env
    for path in (ROOT / "infra/terraform_agentcore").glob("*.tf"):
        text = path.read_text()
        assert "local-exec" not in text
        assert "null_resource" not in text
    assert "upload_file(" not in (ROOT / "scripts/terraform_build.py").read_text()


@pytest.mark.parametrize("mismatch", ["account_id", "region", "project_name"])
def test_deploy_rejects_reusing_state_of_another_environment(monkeypatch, mismatch):
    from scripts import terraform_deploy

    config = {
        "expected_account_id": "123456789012",
        "region": "us-east-1",
        "project_name": "santander-tf-lab",
    }
    value = {"account_id": config["expected_account_id"],
             "region": config["region"], "project_name": config["project_name"]}
    value[mismatch] = "another-target"
    monkeypatch.setattr(terraform_deploy, "terraform", lambda *args, **kwargs: SimpleNamespace(
        stdout=json.dumps({"workshop": {"value": value}})
    ))
    with pytest.raises(RuntimeError, match="STATE_TARGET_MISMATCH"):
        terraform_deploy.check_state_target(config)


def test_terraform_notebook_is_reproducible_and_defaults_to_offline():
    import nbformat

    from scripts.generate_terraform_notebook import OUTPUT, build_notebook
    from scripts.verify_notebooks import check_offline_defaults

    notebook = build_notebook()
    check_offline_defaults(notebook)
    assert nbformat.read(OUTPUT, as_version=4) == notebook
    assert all(not c.outputs and c.execution_count is None
               for c in notebook.cells if c.cell_type == "code")
    assert sum("cleanup_cloud" in c.metadata.get("tags", []) for c in notebook.cells) == 1
    assert sum("cleanup_local" in c.metadata.get("tags", []) for c in notebook.cells) == 1
