"""Contratos reais de protocolo/autorização; nenhum teste acessa AWS."""

import importlib
import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import cedarpy
import jwt
import pytest
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp.types import CallToolResult, TextContent

from santander_demo.banking import client
from santander_demo.banking.spec import (
    DELETE_TOOL,
    LOBS,
    WRITE_TOOLS,
    cedar,
    data_file,
    qualified_tools,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
infra = importlib.import_module("infra.banking.generate")
seed = importlib.import_module("infra.banking.seed_handler").seed

GATEWAY = "arn:aws:bedrock-agentcore:us-east-1:111111111111:gateway/test"
URL = "https://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
REGISTRY = "arn:aws:bedrock-agentcore:us-east-1:111111111111:registry/demo"


@pytest.fixture
def agent_module():
    pytest.importorskip("strands")
    from santander_demo.banking import agent

    return agent


def test_cedar_default_deny_and_forbid_precedence():
    rules = cedar(GATEWAY)
    policy = rules["ReadTools"] + rules["NeverDelete"]

    def decision(tool, text=policy, resource=GATEWAY, principal="AgentCore::OAuthUser"):
        return cedarpy.is_authorized(
            {
                "principal": {"type": principal, "id": "human"},
                "action": {"type": "AgentCore::Action", "id": tool},
                "resource": {"type": "AgentCore::Gateway", "id": resource},
                "context": {},
            },
            text,
            [],
        ).allowed

    read_tools = set(qualified_tools()) - WRITE_TOOLS - {DELETE_TOOL}
    assert len(read_tools) == 12
    assert all(decision(name) for name in read_tools)
    assert all(not decision(name) for name in WRITE_TOOLS | {DELETE_TOOL})
    assert not decision("retail-banking___get_profile", resource=GATEWAY + "other")
    assert not decision("retail-banking___get_profile", principal="Other::Principal")
    assert not decision(DELETE_TOOL, policy + "\npermit(principal, action, resource);")


def test_iac_m2m_cid_policy_and_account_local_iam():
    platform = infra.platform()["Resources"]
    oauth = platform["OAuth"]["Properties"]["Oauth2ProviderConfigInput"][
        "CustomOauth2ProviderConfig"
    ]
    assert "OnBehalfOfTokenExchangeConfig" not in oauth
    assert oauth["ClientSecretSource"] == "EXTERNAL"
    assert "ClientSecret" not in oauth
    authorizer = platform["Gateway"]["Properties"]["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert "AllowedClients" not in authorizer
    assert authorizer["CustomClaims"][0]["InboundTokenClaimName"] == "cid"
    assert platform["Gateway"]["Properties"]["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
    bindings = infra.bindings()["Resources"]
    registry_iam = bindings["RegistryRole"]["Properties"]["Policies"][0]["PolicyDocument"][
        "Statement"
    ]
    create = [s for s in registry_iam if "bedrock-agentcore:CreateRegistry" in s["Action"]]
    assert len(create) == 1 and create[0]["Resource"] == "*"
    assert create[0]["Action"] == ["bedrock-agentcore:CreateRegistry"]
    assert "WriteTools" not in bindings
    assert bindings["NeverDelete"]["Properties"]["ValidationMode"] == "FAIL_ON_ANY_FINDINGS"
    for name, config in LOBS.items():
        target = bindings[config["module"].title() + "Target"]["Properties"]
        credential = target["CredentialProviderConfigurations"][0]["CredentialProvider"][
            "OauthCredentialProvider"
        ]
        assert credential["GrantType"] == "CLIENT_CREDENTIALS"
        resources = infra.lob(name)["Resources"]
        runtime = resources["Runtime"]["Properties"]
        auth = runtime["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
        assert auth["CustomClaims"][0]["AuthorizingClaimMatchValue"]["ClaimMatchValue"] == {
            "MatchValueString": {"Ref": "M2MClientId"}
        }
        assert auth["AllowedWorkloadConfiguration"]["HostingEnvironments"] == [
            {"Arn": {"Ref": "GatewayArn"}}
        ]
        statements = resources["RuntimeRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ]
        actions = {action for stmt in statements for action in stmt["Action"]}
        assert not {"dynamodb:PutItem", "dynamodb:UpdateItem", "sts:AssumeRole"} & actions
        assert resources["Fixtures"]["Type"] == "Custom::BankingFixtures"
    hosted = infra.agent()["Resources"]["Runtime"]["Properties"]
    assert hosted["RequestHeaderConfiguration"]["RequestHeaderAllowlist"] == ["Authorization"]


@pytest.mark.asyncio
async def test_mcp_servers_match_registered_schemas(monkeypatch):
    monkeypatch.setattr("boto3.resource", lambda *a, **kw: MagicMock())
    monkeypatch.setattr("boto3.client", lambda *a, **kw: MagicMock())
    expected = data_file("tools.json")
    for lob, config in LOBS.items():
        module = importlib.import_module("santander_demo.banking.lobs." + config["module"])
        actual = [
            tool.model_dump(mode="json", exclude_none=True)
            for tool in await module.mcp.list_tools()
        ]
        assert actual == expected[lob]


@pytest.mark.asyncio
async def test_lending_mcp_roundtrip_without_aws():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from santander_demo.banking.lobs.lending import mcp; mcp.run(transport='stdio')",
        ],
        env={
            "AWS_EC2_METADATA_DISABLED": "true",
            "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
            "AWS_CONFIG_FILE": "/dev/null",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert len(names) == 6 and "search_lending_policies" in names
            result = await session.call_tool(
                "calculate_emi", {"principal": 1000, "rate": 0, "tenure": 10}
            )
            value = client.tool_json(result)
            value = value.get("result", value)
            assert not result.isError and value["emi"] == 100


def test_seed_never_resets_existing_balances_and_delete_does_not_write():
    tables = data_file("fixtures.json")["retail-banking"]
    dynamodb = MagicMock()
    dynamodb.Table.return_value.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
    )
    event = {
        "RequestType": "Update",
        "ResourceProperties": {
            "Lob": "retail-banking",
            "Tables": {name: "sandbox-" + name for name in tables},
        },
    }
    assert seed(event, dynamodb) == 0
    for call in dynamodb.Table.return_value.put_item.call_args_list:
        assert call.kwargs["ConditionExpression"] == "attribute_not_exists(#pk)"
    dynamodb.reset_mock()
    assert seed({**event, "RequestType": "Delete"}, dynamodb) == 0
    dynamodb.Table.assert_not_called()


def registry_records():
    result = []
    for lob, tools in data_file("tools.json").items():
        result.append(
            {
                "registryArn": REGISTRY,
                "status": "APPROVED",
                "descriptors": {
                    "mcp": {
                        "server": {"inlineContent": json.dumps({"remotes": [{"url": URL}]})},
                        "tools": {
                            "inlineContent": json.dumps(
                                {
                                    "tools": [
                                        {**tool, "name": lob + "___" + tool["name"]}
                                        for tool in tools
                                    ]
                                }
                            )
                        },
                    }
                },
            }
        )
    return result


def test_registry_requires_approval_and_never_selects_bearer_endpoint(agent_module):
    session = MagicMock()
    records = registry_records()
    session.client.return_value.search_registry_records.return_value = {"registryRecords": records}
    assert set(agent_module.discover(session, REGISTRY, URL)) == set(LOBS)
    records[0]["status"] = "DRAFT"
    with pytest.raises(RuntimeError, match="INCOMPLETE"):
        agent_module.discover(session, REGISTRY, URL)
    records[0]["status"] = "APPROVED"
    records[0]["descriptors"]["mcp"]["server"]["inlineContent"] = json.dumps(
        {"remotes": [{"url": "https://example.com/collect"}]}
    )
    with pytest.raises(ValueError, match="ENDPOINT_MISMATCH"):
        agent_module.discover(session, REGISTRY, URL)


def test_registry_pagination_and_cycles(agent_module):
    session = MagicMock()
    records = registry_records()
    session.client.return_value.search_registry_records.side_effect = [
        {"registryRecords": records[:1], "nextToken": "page2"},
        {"registryRecords": records[1:]},
    ]
    assert len(agent_module.discover(session, REGISTRY, URL)) == 3
    session.client.return_value.search_registry_records.side_effect = None
    session.client.return_value.search_registry_records.return_value = {"nextToken": "loop"}
    with pytest.raises(RuntimeError, match="PAGINATION_LOOP"):
        agent_module.discover(session, REGISTRY, URL)


@pytest.mark.parametrize(
    "url",
    [
        "http://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "https://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com.evil.test/mcp",
        URL + "?redirect=https://example.com",
        URL.replace("/mcp", "/other"),
        URL.replace("us-east-1", "us-west-2"),
    ],
)
def test_gateway_rejects_wrong_destination(agent_module, url):
    with pytest.raises(ValueError, match="ENDPOINT"):
        agent_module.checked_gateway(url, "us-east-1")


def config():
    result = json.loads((ROOT / "config/banking.example.json").read_text())
    result.update(
        knowledge_base_id="ABCDEFGHIJ",
        expected_user_sub="human-test",
        model_resource_arns=["arn:aws:bedrock:us-east-1:111111111111:inference-profile/test"],
    )
    result["auth"] = {
        "issuer": "https://test.okta.com/oauth2/demo",
        "discovery_url": "https://test.okta.com/oauth2/demo/.well-known/openid-configuration",
        "audience": "lobfederation",
        "user_client_id": "human-client",
        "m2m_client_id": "m2m-client",
        "m2m_secret_arn": "arn:aws:secretsmanager:us-east-1:111111111111:secret:demo",
        "scope": "lobfederation.invoke",
    }
    return result


def test_four_account_contract_and_bootstrap_plan(tmp_path):
    cfg = config()
    assert client.validate_config(cfg) == cfg
    (tmp_path / "config").mkdir()
    plans = client.prepare_phase(tmp_path, cfg, {}, "bootstrap")
    assert len(plans) == 4
    assert all("--execute" not in p["args"] for p in plans)
    assert all("banking_deploy.py" in p["command"] for p in plans)
    cfg["accounts"]["retail-banking"]["id"] = cfg["accounts"]["platform"]["id"]
    with pytest.raises(ValueError, match="DISTINCT"):
        client.validate_config(cfg)


def test_oidc_signature_audience_cid_and_expected_human(monkeypatch):
    cfg = config()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    discovery = {
        "issuer": cfg["auth"]["issuer"],
        "jwks_uri": "https://test.okta.com/oauth2/demo/v1/keys",
    }
    http = MagicMock()
    http.__enter__.return_value.get.return_value.json.return_value = discovery
    monkeypatch.setattr(client.httpx, "Client", lambda **kw: http)
    jwks = MagicMock()
    jwks.get_signing_key_from_jwt.return_value.key = key.public_key()
    monkeypatch.setattr(client.jwt, "PyJWKClient", lambda url: jwks)
    claims = {
        "iss": cfg["auth"]["issuer"],
        "aud": "lobfederation",
        "sub": "human-test",
        "cid": "human-client",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    token = jwt.encode(claims, key, algorithm="RS256")
    assert client.verify_user_token(token, cfg)["signature"] == "VERIFIED"
    for altered in [{"cid": "m2m-client"}, {"sub": "different-human"}]:
        with pytest.raises(ValueError, match="EXPECTED_USER"):
            client.verify_user_token(jwt.encode({**claims, **altered}, key, algorithm="RS256"), cfg)
    with pytest.raises(jwt.InvalidAudienceError):
        client.verify_user_token(
            jwt.encode({**claims, "aud": "different"}, key, algorithm="RS256"), cfg
        )
    with pytest.raises(jwt.ExpiredSignatureError):
        client.verify_user_token(jwt.encode({**claims, "exp": 1}, key, algorithm="RS256"), cfg)


@pytest.mark.asyncio
async def test_real_mcp_result_wrappers_and_error_classification(monkeypatch):
    session = MagicMock()
    session.call_tool = AsyncMock()
    session.list_tools = AsyncMock(
        return_value=SimpleNamespace(
            tools=[SimpleNamespace(name="lending-wealth___search_lending_policies")],
            nextCursor=None,
        )
    )

    @asynccontextmanager
    async def context(*args):
        yield session

    monkeypatch.setattr(client, "gateway_session", context)
    session.call_tool.return_value = CallToolResult(
        content=[],
        structuredContent={
            "result": json.dumps({"results": [{"text": "synthetic policy", "source": "demo.pdf"}]})
        },
    )
    result = await client.call_tool(
        {"gateway_url": URL}, "test", "lending-wealth___search_lending_policies", {"query": "test"}
    )
    assert result["results"][0]["source"] == "demo.pdf"
    session.call_tool.return_value = CallToolResult(
        content=[], structuredContent={"error": "KB not configured"}
    )
    with pytest.raises(RuntimeError, match="BUSINESS_ERROR"):
        await client.call_tool(
            {"gateway_url": URL}, "test", "lending-wealth___search_lending_policies", {}
        )
    session.call_tool.return_value = CallToolResult(
        isError=True, content=[TextContent(type="text", text="network failed")]
    )
    assert (await client.probe_delete({"gateway_url": URL}, "test"))[
        "outcome"
    ] == "UNCLASSIFIED_ERROR"
    session.call_tool.return_value = CallToolResult(
        isError=True, content=[TextContent(type="text", text="Tool call not allowed")]
    )
    assert (await client.probe_delete({"gateway_url": URL}, "test"))[
        "outcome"
    ] == "POLICY_DENIAL_REPORTED"
    # Um erro de negócio devolvido pelo stub não é uma negativa Cedar.
    session.call_tool.return_value = CallToolResult(
        content=[], structuredContent={"error": "Operation blocked"}
    )
    assert (await client.probe_delete({"gateway_url": URL}, "test"))["outcome"] == "NOT_PROVEN"


def test_strands_wiring_filters_writes_forwards_jwt_and_guardrails(monkeypatch, agent_module):
    from strands.types.collections import PaginatedList

    session = MagicMock()
    session.client.return_value.search_registry_records.return_value = {
        "registryRecords": registry_records()
    }
    session.client.return_value.apply_guardrail.return_value = {
        "action": "NONE",
        "outputs": [],
        "assessments": [],
    }
    mcp = MagicMock()
    mcp.__enter__.return_value = mcp
    mcp.list_tools_sync.side_effect = [
        PaginatedList([SimpleNamespace(tool_name=n) for n in qualified_tools()[:6]], token="next"),
        PaginatedList([SimpleNamespace(tool_name=n) for n in qualified_tools()[6:]], token=None),
    ]
    factory = {}

    def make_mcp(transport):
        factory["transport"] = transport
        return mcp

    model_factory = MagicMock()
    monkeypatch.setattr(agent_module, "BedrockModel", model_factory)
    monkeypatch.setattr(agent_module, "MCPClient", make_mcp)
    instance = MagicMock()
    instance.return_value.message = {"content": [{"text": "Resumo sintético"}]}
    instance.messages = [
        {
            "content": [
                {
                    "toolUse": {
                        "toolUseId": "1",
                        "name": "retail-banking___get_profile",
                        "input": {"sensitive": "should not escape"},
                    }
                }
            ]
        },
        {"content": [{"toolResult": {"toolUseId": "1", "status": "success", "content": []}}]},
    ]
    agent_factory = MagicMock(return_value=instance)
    monkeypatch.setattr(agent_module, "Agent", agent_factory)
    transport = MagicMock()
    monkeypatch.setattr(agent_module, "transport", transport)
    env = {
        "region": "us-east-1",
        "gateway_url": URL,
        "registry_arn": REGISTRY,
        "guardrail_id": "gr",
        "guardrail_version": "1",
        "model_id": "test-model",
    }
    result = agent_module.run_agent("Resumo", "Bearer HUMAN_TEST_TOKEN", env, session)
    factory["transport"]()
    transport.assert_called_once_with(URL, "Bearer HUMAN_TEST_TOKEN")
    assert model_factory.call_args.kwargs["boto_session"] is session
    assert {t.tool_name for t in agent_factory.call_args.kwargs["tools"]} == set(
        qualified_tools()
    ) - WRITE_TOOLS - {DELETE_TOOL}
    assert session.client.return_value.apply_guardrail.call_count == 2
    serialized = json.dumps(result)
    assert "HUMAN_TEST_TOKEN" not in serialized and "sensitive" not in serialized
    assert result["tool_calls"] == [
        {"tool": "retail-banking___get_profile", "lob": "retail-banking", "status": "success"}
    ]


def test_guardrail_preserves_redaction_and_stops_blocks(agent_module):
    bedrock = MagicMock()
    bedrock.apply_guardrail.return_value = {
        "action": "GUARDRAIL_INTERVENED",
        "outputs": [{"text": "SSN: {US_SOCIAL_SECURITY_NUMBER}"}],
        "assessments": [
            {"sensitiveInformationPolicy": {"piiEntities": [{"action": "ANONYMIZED"}]}}
        ],
    }
    text, blocked, changed = agent_module.guard_text(bedrock, "g", "1", "SSN: 123-45-6789", "INPUT")
    assert changed and not blocked and "123-45" not in text
    bedrock.apply_guardrail.return_value["assessments"] = [
        {"contentPolicy": {"filters": [{"action": "BLOCKED"}]}}
    ]
    assert agent_module.guard_text(bedrock, "g", "1", "test", "INPUT")[1] is True


def test_evidence_does_not_claim_unobserved_lobs():
    result = {
        "response": "synthetic details",
        "tool_calls": [
            {"tool": "retail-banking___get_profile", "lob": "retail-banking", "status": "success"},
            {
                "tool": "transaction-banking___get_payments",
                "lob": "transaction-banking",
                "status": "error",
            },
        ],
    }
    evidence = client.sanitized_evidence(
        {"lob_runtime_arns": dict.fromkeys(LOBS)}, result, {"outcome": "NOT_RUN"}
    )
    assert not evidence["three_lobs_observed"]
    assert evidence["lobs_with_successful_tool_results"] == ["retail-banking"]
    assert "synthetic details" not in json.dumps(evidence)
