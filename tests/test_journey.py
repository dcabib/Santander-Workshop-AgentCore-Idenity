import copy
import json
from unittest.mock import Mock
from uuid import UUID

import pytest
from mcp.types import CallToolResult, TextContent

from infra.journey.generate import generate
from santander_demo.contracts import DemoError
from santander_demo.governance import Limits, LocalQuotaLedger, local_quota_demo
from santander_demo.journey.client import PHASES, prepare_phase, validate_config
from santander_demo.journey.evidence import acceptance, classify_error, statement_evidence
from santander_demo.journey.runtime import delegated_token, validate_record, verified_identity
from santander_demo.journey.spec import (
    IDENTITY_QUERY,
    canary_query,
    evaluate,
    local_matrix,
    tool_name,
)
from santander_demo.knowledge import Document, KnowledgeLab, local_knowledge_demo


def example_config():
    from pathlib import Path

    config = json.loads(
        (Path(__file__).resolve().parents[1] / "config/journey.example.json").read_text()
    )
    config["tenant_id"] = str(UUID(int=1))
    config["login_client_id"] = str(UUID(int=2))
    config["users"] = {"a": str(UUID(int=3)), "b": str(UUID(int=4))}
    for i, (name, account) in enumerate(config["accounts"].items(), 5):
        account["gateway_client_id"] = str(UUID(int=i))
        if name != "data":
            account["gateway_secret_arn"] = account["gateway_secret_arn"].replace("REPLACE", "demo")
    for i, agent in enumerate(config["agents"].values(), 8):
        agent["client_id"] = str(UUID(int=i))
        agent["secret_arn"] = agent["secret_arn"].replace("REPLACE", "demo")
    db = config["databricks"]
    db["host"] = "https://adb-12345.6.azuredatabricks.net"
    db["mcp_url"] = db["host"] + "/api/2.0/mcp/sql"
    db["secret_arn"] = db["secret_arn"].replace("REPLACE", "demo")
    db["client_id"] = str(UUID(int=10))
    db["public_client_exchange_enabled"] = True
    return config


def result(body, *, error=False):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(body))], isError=error)


def test_same_user_different_agent_and_sql_boundary():
    rows = local_matrix()["cases"]
    assert len(rows) == 8
    assert rows[0]["decision"] == "ALLOW"
    assert rows[1]["decision"] == "DENY"
    assert rows[-1]["decision"] == "DENY"
    assert local_matrix()["aws_oauth_databricks"] == "NOT_RUN"


@pytest.mark.parametrize("missing", ["azp", "tid", "oid", "ver", "scp"])
def test_hub_fails_closed_on_missing_verified_claims(missing):
    claims = {
        "sub": "s",
        "azp": "risks",
        "tid": "tenant-demo",
        "oid": "u",
        "ver": "2.0",
        "scp": "access_as_user",
    }
    claims.pop(missing)
    assert not evaluate(
        "platform",
        claims,
        tool_name("riscos"),
        {"query": IDENTITY_QUERY},
        callers={"riscos": "risks", "fraude": "fraud"},
        users=["u"],
        tables={"riscos": "a.r.canary", "fraude": "a.f.canary"},
    )


@pytest.mark.parametrize(
    "table", ["a.b.c;DROP TABLE x", "a.b.`c`", "a.b.c --", "a.b", "a.b.c\n", "a.b.c UNION SELECT 1"]
)
def test_no_sql_injection_through_table_identifier(table):
    with pytest.raises(ValueError):
        canary_query(table)


def test_valid_configuration_and_cross_cloud_host_pinning():
    config = example_config()
    assert validate_config(config)
    for change in ("host", "mcp_url"):
        bad = copy.deepcopy(config)
        bad["databricks"][change] += ".attacker.example"
        with pytest.raises(ValueError):
            validate_config(bad)
    bad = copy.deepcopy(config)
    bad["databricks"]["oauth_scope"] = "ai-gateway"
    with pytest.raises(ValueError):
        validate_config(bad)
    config["databricks"].update(
        endpoint_mode="unity_dbsql",
        oauth_scope="ai-gateway",
        mcp_url=config["databricks"]["host"] + "/ai-gateway/mcp-services/system.ai.dbsql",
    )
    assert validate_config(config)


def test_same_oid_and_shared_app_are_rejected():
    config = example_config()
    config["users"]["b"] = config["users"]["a"]
    with pytest.raises(ValueError, match="TWO_DISTINCT_USERS"):
        validate_config(config)
    config = example_config()
    config["agents"]["fraude"]["client_id"] = config["agents"]["riscos"]["client_id"]
    with pytest.raises(ValueError, match="SIX_DISTINCT"):
        validate_config(config)


def test_exchange_only_uses_user_bound_workload_and_obo():
    client = Mock()
    client.get_workload_access_token_for_jwt.return_value = {"workloadAccessToken": "wat"}
    client.get_resource_oauth2_token.return_value = {"accessToken": "delegated"}
    token = delegated_token(
        client, {"workload_name": "risk", "provider_name": "obo", "hub_audience": "hub"}, "jwt"
    )
    assert token == "delegated"
    client.get_workload_access_token_for_jwt.assert_called_once_with(
        workloadName="risk", userToken="jwt"
    )
    request = client.get_resource_oauth2_token.call_args.kwargs
    assert request["oauth2Flow"] == "ON_BEHALF_OF_TOKEN_EXCHANGE"
    assert request["workloadIdentityToken"] == "wat"
    assert request["customParameters"] == {"requested_token_use": "on_behalf_of"}
    client.get_resource_oauth2_token.return_value = {}
    with pytest.raises(RuntimeError):
        delegated_token(
            client, {"workload_name": "risk", "provider_name": "obo", "hub_audience": "hub"}, "jwt"
        )


def test_runtime_checks_audience_and_actual_agent(monkeypatch):
    from santander_demo.identity import JwtVerifier, LocalIssuer

    issuer = LocalIssuer()
    monkeypatch.setattr(
        "santander_demo.journey.runtime.verify_entra",
        lambda token, **kw: JwtVerifier(
            key=issuer._key.public_key(),
            issuer=issuer.issuer,
            audience=kw["audience"],
            tenant=kw["tenant"],
        ).verify(token),
    )
    config = {
        "tenant": issuer.tenant,
        "audience": "agent-r",
        "caller": "origin-gw",
        "hub_audience": "hub",
        "subject_claim": "preferred_username",
    }
    good = issuer.token(
        aud="agent-r",
        azp="origin-gw",
        scp="access_as_user",
        preferred_username="test@example.invalid",
    )
    assert verified_identity(good, config).claims["oid"]
    with pytest.raises(ValueError, match="DELEGATION"):
        verified_identity(
            issuer.token(aud="agent-r", azp="spoofed-agent", scp="access_as_user"), config
        )
    with pytest.raises(DemoError, match="AUTH_INVALID_TOKEN"):
        verified_identity(good, config, hub=True)
    hub = issuer.token(
        aud="hub", azp="agent-r", scp="access_as_user", preferred_username="test@example.invalid"
    )
    assert verified_identity(hub, config, hub=True).claims["azp"] == "agent-r"


@pytest.mark.parametrize(
    "arrived,expected,outcome",
    [
        ("human@example.invalid", "human@example.invalid", "PER_USER_VERIFIED"),
        ("shared@example.invalid", "human@example.invalid", "IDENTITY_NOT_PROVEN"),
        (str(UUID(int=5)), "human@example.invalid", "IDENTITY_NOT_PROVEN"),
        ("human@example.invalid", "", "IDENTITY_NOT_PROVEN"),
    ],
)
def test_databricks_compares_actual_principal(arrived, expected, outcome):
    proof = statement_evidence(
        result(
            {
                "statement_id": "query-1",
                "status": {"state": "SUCCEEDED"},
                "result": {"data_array": [[arrived, "1"]]},
            }
        ),
        expected,
    )
    assert proof["outcome"] == outcome
    assert proof["query_id"] == "query-1"
    assert "@" not in json.dumps(proof)


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Token exchange failed: PERMISSION_DENIED", "AUTH_OR_EXCHANGE_ERROR"),
        ("Tool call not allowed", "POLICY_DENY_REPORTED"),
        ("[INSUFFICIENT_PRIVILEGES] SELECT is not granted", "SOURCE_GRANT_DENY_REPORTED"),
        ("Timeout connecting", "UNCLASSIFIED_ERROR"),
        ("SQL parse error", "UNCLASSIFIED_ERROR"),
    ],
)
def test_errors_never_silently_become_successful_denial_proofs(message, expected):
    assert classify_error(message) == expected


def test_pending_query_is_not_proof_and_incomplete_trace_cannot_pass_acceptance():
    assert (
        statement_evidence(result({"status": {"state": "RUNNING"}, "statement_id": "q"}), "test")[
            "outcome"
        ]
        == "QUERY_INCOMPLETE"
    )
    assert acceptance([])["status"] == "PENDING_EVIDENCE"
    rows = [
        {
            "case": c,
            "mode": "AWS_LIVE",
            "outcome": o,
            "identity_verified": True,
            "user_ref": u,
            "query_id": "q",
        }
        for c, o, u in [
            ("a_riscos", "PER_USER_VERIFIED", "a"),
            ("a_fraude", "PER_USER_VERIFIED", "a"),
            ("a_wrong_agent", "POLICY_DENY_REPORTED", "a"),
            ("b_sem_grant", "SOURCE_GRANT_DENY_REPORTED", "b"),
        ]
    ]
    report = acceptance(rows)
    assert report["status"] == "PENDING_EVIDENCE"
    assert "a_wrong_agent:backend_non_execution" in report["missing"]
    assert "a_riscos:gateway_logs" in report["missing"]


def test_registry_requires_owner_instance_version_and_approved_pinned_endpoint():
    config = {
        "registry_arn": "arn:catalog",
        "project": "journey",
        "hub_url": "https://approved.example/mcp",
    }
    record = {
        "registryArn": "arn:catalog",
        "status": "APPROVED",
        "descriptors": {
            "mcp": {
                "server": {
                    "inlineContent": json.dumps(
                        {
                            "name": "com.santander.demo/riscos",
                            "version": "1.0.0",
                            "_meta": {
                                "com.santander/owner": "dados",
                                "com.santander/instance": "journey",
                            },
                            "remotes": [{"type": "streamable-http", "url": config["hub_url"]}],
                        }
                    )
                },
                "tools": {"inlineContent": json.dumps({"tools": [{"name": tool_name("riscos")}]})},
            }
        },
    }
    assert validate_record(record, config, "riscos")
    record["status"] = "PENDING_APPROVAL"
    assert not validate_record(record, config, "riscos")
    record["status"] = "APPROVED"
    record["descriptors"]["mcp"]["server"]["inlineContent"] = record["descriptors"]["mcp"][
        "server"
    ]["inlineContent"].replace("approved.example", "attacker.example")
    with pytest.raises(ValueError, match="REGISTRY_CONTRACT"):
        validate_record(record, config, "riscos")


def test_iac_has_three_gateways_two_hosted_agents_and_native_obo():
    docs = generate()
    assert len(docs) == 10
    for account in ("origin", "platform", "data"):
        gateway = docs[account + "-gateway"]["Resources"]["Gateway"]["Properties"]
        assert gateway["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
        assert gateway["AuthorizerType"] == "CUSTOM_JWT"
        assert all(
            r["Properties"]["CredentialProviderConfigurations"][0]["CredentialProvider"][
                "OauthCredentialProvider"
            ]["GrantType"]
            == "TOKEN_EXCHANGE"
            for r in docs[account + "-bindings"]["Resources"].values()
            if r["Type"].endswith("GatewayTarget")
        )
    provider = docs["data-gateway"]["Resources"]["OAuth"]["Properties"][
        "Oauth2ProviderConfigInput"
    ]["CustomOauth2ProviderConfig"]
    assert provider["OnBehalfOfTokenExchangeConfig"] == {
        "GrantType": "TOKEN_EXCHANGE",
        "TokenExchangeGrantTypeConfig": {"ActorTokenContent": "NONE"},
    }
    assert "ClientAuthenticationMethod" not in provider  # no unsupported enum NONE
    for name in ("riscos", "fraude"):
        runtime = docs[name + "-agent"]["Resources"]["Runtime"]["Properties"]
        assert runtime["AgentRuntimeArtifact"]["CodeConfiguration"]["EntryPoint"] == [
            "python",
            "journey_runtime_main.py",
        ]
        assert runtime["AuthorizerConfiguration"]["CustomJWTAuthorizer"][
            "AllowedWorkloadConfiguration"
        ]
        assert (
            docs["registry"]["Resources"][name.title() + "RecordApproval"]["Condition"]
            == "ApproveRecords"
        )


def test_all_phase_parameters_match_iac_contract_and_never_execute_cloud(tmp_path, monkeypatch):
    config = example_config()
    docs = generate()
    (tmp_path / "config").mkdir()

    def outputs(config, sessions, account, name):
        return {
            "ArtifactBucket": "bucket",
            "GatewayId": "gw",
            "GatewayArn": "arn:gw",
            "GatewayUrl": "https://example.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
            "PolicyEngineId": "engine",
            "OAuthProviderArn": "arn:provider",
            "RuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:111111111111:runtime/risk-123",
            "RegistryArn": "arn:registry",
            "RegistryConsumerRoleArn": "arn:role",
        }

    monkeypatch.setattr("santander_demo.journey.client.outputs", outputs)
    for phase in PHASES:
        for plan in prepare_phase(tmp_path, config, {}, phase):
            parameters = json.loads(PathArg(plan["args"]).read_text())
            defined = docs[plan["template"]]["Parameters"]
            assert set(parameters) <= set(defined), (phase, set(parameters) - set(defined))
            required = {k for k, v in defined.items() if "Default" not in v} - {"ArtifactKey"}
            assert required <= set(parameters), (phase, required - set(parameters))
            assert "--execute" not in plan["args"]
    config["databricks"]["public_client_exchange_enabled"] = False
    with pytest.raises(ValueError, match="ENABLEMENT"):
        prepare_phase(tmp_path, config, {}, "data-bindings")


def PathArg(args):
    from pathlib import Path

    return Path(args[args.index("--parameters") + 1])


def test_quota_contract_separates_time_tokens_and_monthly_budget():
    assert [r["decision"] for r in local_quota_demo()] == [
        "ALLOW",
        "ALLOW",
        "QPM_DENY",
        "TPM_DENY",
        "BUDGET_DENY",
    ]
    ledger, limits = LocalQuotaLedger(), Limits(1, 10, 20)
    assert (
        ledger.reserve("a", "t", tokens=5, micro_usd=10, now=0, limits=limits)["decision"]
        == "ALLOW"
    )
    assert (
        ledger.reserve("a", "t", tokens=5, micro_usd=10, now=0, limits=limits)["decision"]
        == "QPM_DENY"
    )
    assert (
        ledger.reserve("b", "t", tokens=5, micro_usd=10, now=0, limits=limits)["decision"]
        == "ALLOW"
    )
    assert (
        ledger.reserve("a", "t", tokens=5, micro_usd=11, now=60, limits=limits)["decision"]
        == "BUDGET_DENY"
    )


def test_acl_rechecked_for_shared_index_and_memory_on_update_delete():
    report = local_knowledge_demo()
    assert report["visibility_before"]["user-riscos"] == ["R1"]
    assert report["visibility_before"]["user-fraude"] == ["F1"]
    assert report["revoked_acl_in_memory"] == "DENIED"
    lab = KnowledgeLab()
    lab.register(Document("x", "synthetic", "sensitive", frozenset({"bdag-riscos"}), 1))
    assert lab.retrieve("unknown", "sensitive") == []
    with pytest.raises(ValueError, match="ACCESS"):
        lab.remember("user-fraude", "s", ["x"])
    with pytest.raises(ValueError, match="VERSION"):
        lab.update(Document("x", "synthetic", "updated", frozenset({"bdag-riscos"}), 5))


@pytest.mark.parametrize(
    "scenario,expected,calls",
    [
        ("allow", "PER_USER_VERIFIED", 2),
        ("policy", "POLICY_DENY_REPORTED", 1),
        ("grant", "SOURCE_GRANT_DENY_REPORTED", 2),
    ],
)
async def test_hosted_agent_uses_real_mcp_protocol_and_delegated_token(
    monkeypatch, scenario, expected, calls
):
    import httpx

    from santander_demo.identity import JwtVerifier, LocalIssuer
    from santander_demo.journey import runtime

    issuer = LocalIssuer()
    claim = "person@example.invalid"
    config = {
        "tenant": issuer.tenant,
        "audience": "agent-r",
        "caller": "origin-gw",
        "hub_audience": "hub",
        "subject_claim": "email",
        "region": "us-east-1",
        "hub_url": "https://demo.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "agent": "riscos",
        "tables": {"riscos": "demo.r.canary"},
        "workload_name": "risk",
        "provider_name": "risk-obo",
    }
    inbound = issuer.token(aud="agent-r", azp="origin-gw", scp="access_as_user", email=claim)
    outbound = issuer.token(aud="hub", azp="agent-r", scp="access_as_user", email=claim)
    monkeypatch.setattr(
        runtime,
        "verify_entra",
        lambda token, **kw: JwtVerifier(
            key=issuer._key.public_key(),
            issuer=issuer.issuer,
            audience=kw["audience"],
            tenant=kw["tenant"],
        ).verify(token),
    )
    monkeypatch.setattr(runtime, "discover", lambda *_: {"status": "APPROVED"})
    session = Mock()
    session.client.return_value.get_workload_access_token_for_jwt.return_value = {
        "workloadAccessToken": "wat"
    }
    session.client.return_value.get_resource_oauth2_token.return_value = {"accessToken": outbound}
    invoked = []

    def handler(request):
        assert request.headers["authorization"] == "Bearer " + outbound
        rpc = json.loads(request.content)
        if rpc["method"].startswith("notifications/"):
            return httpx.Response(202)
        if rpc["method"] == "initialize":
            body = {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-double", "version": "1"},
            }
        elif rpc["method"] == "tools/list":
            from santander_demo.journey.spec import SQL_SCHEMA

            body = {"tools": [{**SQL_SCHEMA, "name": tool_name("riscos")}]}
        else:
            assert rpc["method"] == "tools/call"
            invoked.append(rpc["params"])
            assert rpc["params"]["_meta"]["com.santander/request_id"] == str(UUID(int=12))
            if scenario == "policy":
                body = {
                    "isError": True,
                    "content": [{"type": "text", "text": "Tool call not allowed"}],
                }
            elif scenario == "grant" and len(invoked) == 2:
                body = result(
                    {"status": {"state": "FAILED", "error": {"error_code": "PERMISSION_DENIED"}}}
                ).model_dump()
            else:
                body = result(
                    {
                        "statement_id": "query-" + str(len(invoked)),
                        "status": {"state": "SUCCEEDED"},
                        "result": {"data_array": [[claim, "1"]]},
                    }
                ).model_dump()
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": rpc["id"], "result": body},
            headers={"x-amzn-requestid": "http-" + str(len(invoked))},
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        runtime.httpx,
        "AsyncClient",
        lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw),
    )
    report = await runtime.consult(config, inbound, "riscos", str(UUID(int=12)), session=session)
    assert report["outcome"] == expected
    assert len(invoked) == calls
    assert report["identity_verified"] is (scenario != "policy")
    assert report["gateway_log_correlation_verified"] is False
    assert report["hub_gateway_request_ids"]
    assert inbound not in json.dumps(report) and outbound not in json.dumps(report)
    assert claim not in json.dumps(report)


async def test_runtime_entry_reads_bearer_from_http_not_arguments(monkeypatch):
    import httpx

    from santander_demo.journey import runtime

    observed = []

    async def consult(config, token, capability, request_id):
        observed.append((config["agent"], token, capability))
        return {"request_id": request_id, "agent": config["agent"]}

    monkeypatch.setattr(runtime, "consult", consult)
    server = runtime.create_server({"agent": "riscos"})
    server.settings.json_response = True
    app = server.streamable_http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
        ) as http:
            for token, error in [("Bearer signed-jwt", False), ("", True)]:
                response = await http.post(
                    "/mcp",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Authorization": token,
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "consultar",
                            "arguments": {"capacidade": "fraude", "request_id": str(UUID(int=5))},
                        },
                    },
                )
                assert response.status_code == 200
                assert response.json()["result"].get("isError", False) is error
    assert observed == [("riscos", "signed-jwt", "fraude")]
