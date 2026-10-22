import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from santander_demo.banking.spec import LOBS
from santander_demo.federation import client, runtime_identity, spec
from santander_demo.identity import Identity

ROOT = Path(__file__).resolve().parents[1]


def config():
    def uid(n):
        return f"00000000-0000-0000-0000-{n:012d}"

    value = json.loads((ROOT / "config/federation.example.json").read_text())
    value.update(
        tenant_id=uid(1),
        login_client_id=uid(2),
        expected_user_oid=uid(3),
        knowledge_base_id="ABC1234567",
    )
    for i, (name, account) in enumerate(value["accounts"].items()):
        account["gateway_client_id"] = uid(10 + i)
        account["allowed_user_oids"] = [uid(3)]
        account["gateway_secret_arn"] = (
            f"arn:aws:secretsmanager:us-east-1:{account['id']}:secret:gateway-abcdef"
        )
        if name != "platform":
            account["runtime_client_id"] = uid(20 + i)
    return value


def test_local_matrix_has_independent_denials():
    result = spec.local_matrix()
    assert result["oauth_and_aws"] == "NOT_RUN"
    assert [(c["platform_policy"], c["retail_policy_isolated"]) for c in result["cases"]] == [
        ("ALLOW", "ALLOW"),
        ("DENY", "ALLOW"),
        ("ALLOW", "DENY"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"tid": "other"},
        {"oid": "other"},
        {"azp": "notebook-app"},
        {"scp": None},
        {"scp": "access_as_user.admin"},
        {"scp": "other access_as_user"},
    ],
)
def test_domain_cedar_denies_incorrect_identity(change):
    claims = {"tid": "tenant", "oid": "user", "azp": "platform-app", "scp": spec.SCOPE, **change}
    assert not spec.evaluate(
        "retail-banking",
        claims,
        spec.local_name("get_profile"),
        {"customer_id": "C003"},
        gateway_arn="arn:local:retail",
        tenant="tenant",
        caller="platform-app",
        users=["user"],
    )


@pytest.mark.parametrize(
    "action",
    ["backend___update_balance", "backend___delete_customer", "get_profile", "backend___unknown"],
)
def test_domain_denies_writes_and_unknown_names(action):
    assert not spec.evaluate(
        "retail-banking",
        {"tid": "t", "oid": "u", "azp": "c", "scp": spec.SCOPE},
        action,
        {"customer_id": "C003"},
        gateway_arn="arn:local:retail",
        tenant="t",
        caller="c",
        users=["u"],
    )


def test_nested_schemas_have_complete_short_unambiguous_names():
    tools = spec.tools_by_lob()
    assert sum(map(len, tools.values())) == 19
    assert sum(len(spec.readable(lob, central=True)) for lob in LOBS) == 15
    assert "retail___backend___get_profile" in tools["retail-banking"]
    assert all(len(name) <= 64 for names in tools.values() for name in names)


def test_templates_enforce_each_boundary_and_keep_registry_off_invocation_path():
    from infra.federation.generate import generate

    templates = generate()
    assert len(templates) == 13
    for account in spec.ACCOUNTS:
        gateway = templates[account + "-gateway"]["Resources"]
        props = gateway["Gateway"]["Properties"]
        assert props["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
        claims = props["AuthorizerConfiguration"]["CustomJWTAuthorizer"]["CustomClaims"]
        assert {c["InboundTokenClaimName"] for c in claims} == {"tid", "azp", "ver", "scp"}
        assert "AllowedClients" not in props["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
        oauth = gateway["OAuth"]["Properties"]["Oauth2ProviderConfigInput"][
            "CustomOauth2ProviderConfig"
        ]
        assert oauth["OnBehalfOfTokenExchangeConfig"]["GrantType"] == "JWT_AUTHORIZATION_GRANT"
        assert oauth["ClientSecretConfig"]["SecretId"] == {"Ref": "GatewaySecretArn"}
        bindings = templates[account + "-bindings"]["Resources"]
        for target in [
            v["Properties"] for v in bindings.values() if v["Type"].endswith("::GatewayTarget")
        ]:
            credential = target["CredentialProviderConfigurations"][0]["CredentialProvider"][
                "OauthCredentialProvider"
            ]
            assert credential["GrantType"] == "TOKEN_EXCHANGE"
            assert credential["CustomParameters"] == {"requested_token_use": "on_behalf_of"}
            tools = json.loads(
                target["TargetConfiguration"]["Mcp"]["McpServer"]["McpToolSchema"]["InlinePayload"]
            )["tools"]
            assert all(t["name"].startswith("backend___") for t in tools) == (account == "platform")
        assert bindings["ReadDelegated"]["Properties"]["EnforcementMode"] == "ACTIVE"
        if account != "platform":
            backend = templates[account + "-backend"]["Resources"]["Runtime"]["Properties"]
            assert backend["AuthorizerConfiguration"]["CustomJWTAuthorizer"][
                "AllowedWorkloadConfiguration"
            ] == {"HostingEnvironments": [{"Arn": {"Ref": "GatewayArn"}}]}
            assert backend["RequestHeaderConfiguration"]["RequestHeaderAllowlist"] == [
                "Authorization"
            ]
    records = templates["registry"]["Resources"]
    tools = json.loads(
        records["RetailRecord"]["Properties"]["Descriptors"]["mcp"]["tools"]["inlineContent"]
    )["tools"]
    assert {t["name"] for t in tools} == set(spec.tools_by_lob()["retail-banking"])
    assert not any(v["Type"].endswith("::GatewayTarget") for v in records.values())


def test_multiple_users_substitute_into_valid_cedar():
    import cedarpy

    from infra.federation.generate import binding

    source, mapping = binding("platform")["Resources"]["ReadDelegated"]["Properties"]["Definition"][
        "Cedar"
    ]["Statement"]["Fn::Sub"]
    assert mapping["UserList"]["Fn::Join"][0] == '","'
    for key, value in {
        "GatewayArn": "arn:local:platform",
        "TenantId": "t",
        "CallerClientId": "c",
        "UserList": 'user1","user2',
    }.items():
        source = source.replace("${" + key + "}", value)
    principal = {"type": "AgentCore::OAuthUser", "id": "subject"}
    result = cedarpy.is_authorized(
        {
            "principal": principal,
            "action": {"type": "AgentCore::Action", "id": "retail___backend___get_profile"},
            "resource": {"type": "AgentCore::Gateway", "id": "arn:local:platform"},
            "context": {},
        },
        source,
        [
            {
                "uid": principal,
                "attrs": {},
                "parents": [],
                "tags": {
                    "tid": "t",
                    "oid": "user2",
                    "azp": "c",
                    "scp": spec.SCOPE,
                },
            }
        ],
    )
    assert result.allowed


def test_configuration_requires_account_local_secrets_and_distinct_audiences():
    value = config()
    assert client.validate_config(value) is value
    value["accounts"]["retail-banking"]["gateway_secret_arn"] = value["accounts"]["platform"][
        "gateway_secret_arn"
    ]
    with pytest.raises(ValueError, match="LOCAL_ACCOUNT"):
        client.validate_config(value)
    value = config()
    value["accounts"]["retail-banking"]["gateway_client_id"] = value["accounts"]["platform"][
        "gateway_client_id"
    ]
    with pytest.raises(ValueError, match="DISTINCT_ENTRA"):
        client.validate_config(value)


def test_prepare_bindings_connects_gateways_then_local_runtime(tmp_path, monkeypatch):
    value = config()

    def fake_outputs(config, sessions, account, suffix):
        return {
            "GatewayId": account,
            "GatewayArn": "arn:" + account,
            "PolicyEngineId": "p",
            "OAuthProviderArn": "arn:provider",
            "GatewayUrl": f"https://{account}.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
            "RuntimeArn": f"arn:aws:bedrock-agentcore:us-east-1:{value['accounts'][account]['id']}:runtime/test",
        }

    monkeypatch.setattr(client, "outputs", fake_outputs)
    plans = client.prepare_phase(tmp_path, value, {}, "platform-bindings")
    params = json.loads(Path(plans[0]["args"][-1]).read_text())
    assert params["RetailEndpoint"].endswith(".amazonaws.com/mcp")
    assert (
        params["RetailScope"]
        == f"api://{value['accounts']['retail-banking']['gateway_client_id']}/.default"
    )
    plans = client.prepare_phase(tmp_path, value, {}, "domain-bindings")
    params = json.loads(Path(plans[0]["args"][-1]).read_text())
    assert "/runtimes/" in params["RetailEndpoint"]
    assert (
        params["RetailScope"]
        == f"api://{value['accounts']['retail-banking']['runtime_client_id']}/.default"
    )


def test_runtime_identity_checks_verified_claims_and_sanitizes(monkeypatch):
    claims = {
        "sub": "sub",
        "tid": "tenant",
        "oid": "user",
        "azp": "local-gw",
        "aud": "runtime",
        "scp": spec.SCOPE,
        "ver": "2.0",
    }
    verify = Mock(return_value=Identity(claims))
    monkeypatch.setattr(runtime_identity, "verify_entra", verify)
    contract = {
        "tenant": "tenant",
        "audience": "runtime",
        "caller": "local-gw",
        "lob": "retail-banking",
    }
    result = runtime_identity.verify_runtime_identity("Bearer test", contract)
    verify.assert_called_once_with("test", tenant="tenant", audience="runtime", version="2.0")
    assert result["user_ref"] == Identity(claims).summary()["user_ref"]
    assert "oid" not in result and "sub" not in result and "token" not in result
    claims["azp"] = "platform-gw"
    with pytest.raises(ValueError, match="DELEGATION"):
        runtime_identity.verify_runtime_identity("Bearer test", contract)


async def test_whoami_is_an_actual_mcp_tool_with_no_user_supplied_claims(monkeypatch):
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setenv(
        "FEDERATED_IDENTITY",
        json.dumps({"tenant": "t", "audience": "a", "caller": "c", "lob": "retail-banking"}),
    )
    mcp = FastMCP("test")
    runtime_identity.register(mcp)
    tool = (await mcp.list_tools())[0]
    assert tool.name == "whoami"
    assert tool.inputSchema["properties"] == {}


async def test_whoami_reads_transport_header_and_verifies_signed_jwt(monkeypatch):
    import httpx
    from mcp.server.fastmcp import FastMCP
    from mcp.types import CallToolResult

    from santander_demo.cloud import tool_json
    from santander_demo.identity import LocalIssuer

    issuer = LocalIssuer()
    config = {
        "tenant": issuer.tenant,
        "audience": issuer.audience,
        "caller": "retail-gateway",
        "lob": "retail-banking",
    }
    monkeypatch.setenv("FEDERATED_IDENTITY", json.dumps(config))

    def verify_local(token, *, tenant, audience, version):
        assert (tenant, audience, version) == (issuer.tenant, issuer.audience, "2.0")
        return issuer.verifier.verify(token)

    # Substitui somente a fonte de chaves; assinatura RSA e contrato MCP são reais.
    monkeypatch.setattr(runtime_identity, "verify_entra", verify_local)
    mcp = FastMCP("test", stateless_http=True, json_response=True)
    runtime_identity.register(mcp)
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as http:
            for scope, should_fail in [(spec.SCOPE, False), (None, True)]:
                token = issuer.token("ambos", "retail-gateway", scp=scope)
                response = await http.post(
                    "/mcp",
                    headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "whoami", "arguments": {}},
                    },
                )
                assert response.status_code == 200
                result = response.json()["result"]
                assert result.get("isError", False) is should_fail
                if not should_fail:
                    data = tool_json(CallToolResult.model_validate(result))
                    assert data["caller"] == "retail-gateway"
                    assert data["delegated"]
                    assert token not in response.text


async def test_chain_rejects_changed_user_or_actor(monkeypatch):
    value = config()
    monkeypatch.setattr(client, "verify_token", lambda *_: {"user_ref": "expected"})

    async def response(environment, token, tool, arguments):
        lob = next(name for name in LOBS if tool.startswith(spec.PREFIXES[name] + "___"))
        return {
            "mode": "AWS_VERIFIED_JWT",
            "lob": lob,
            "user_ref": "expected",
            "caller": value["accounts"][lob]["gateway_client_id"],
            "audience": value["accounts"][lob]["runtime_client_id"],
            "delegated": True,
        }

    monkeypatch.setattr(client, "call_tool", response)
    result = await client.verify_chain({}, "token", value)
    assert len(result["obo"]) == 3

    async def changed(*args):
        return {**await response(*args), "user_ref": "different"}

    monkeypatch.setattr(client, "call_tool", changed)
    with pytest.raises(RuntimeError, match="END_TO_END"):
        await client.verify_chain({}, "token", value)


def test_notebook_agent_maps_federated_tool_trace_without_expanding_permissions(monkeypatch):
    module = importlib.import_module("santander_demo.federation.agent")
    run = Mock(
        return_value={
            "tool_calls": [
                {"tool": "retail___backend___get_profile", "lob": "retail", "status": "success"}
            ]
        }
    )
    monkeypatch.setattr(module, "run_banking_agent", run)
    result = module.run_agent("question", "token", {}, SimpleNamespace())
    assert result["tool_calls"][0]["lob"] == "retail-banking"
    config_arg = run.call_args.args[2]
    assert config_arg["tools_by_lob"] == spec.tools_by_lob()
    assert not any(
        "delete_customer" in tool or "update_balance" in tool for tool in config_arg["read_tools"]
    )
