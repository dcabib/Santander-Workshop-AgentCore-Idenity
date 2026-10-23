import copy
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import botocore.session
import httpx
import jwt
import pytest
from botocore.stub import Stubber
from botocore.validate import validate_parameters
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import Context, FastMCP

from infra.rag.generate import generate
from santander_demo.contracts import DemoError
from santander_demo.identity import JwtVerifier
from santander_demo.rag import client, deployment, seed
from santander_demo.rag.contract import (
    DOMAINS,
    QUESTION,
    SCOPE,
    TOOL,
    connector_configuration,
    evaluate,
)
from santander_demo.rag.corpus import DOCUMENTS, allowed_documents, corpus_digest, objects
from santander_demo.rag.local import (
    LOCAL_GATEWAY,
    LOCAL_USERS,
    LocalKnowledgeBase,
    LocalModel,
    LocalRagLab,
    demo,
)


@pytest.fixture
def config():
    c = json.loads(Path("config/rag.entra.example.json").read_text())
    c.update(
        tenant_id=str(uuid4()),
        login_client_id=str(uuid4()),
        broker_client_id=str(uuid4()),
        gateway_client_id=str(uuid4()),
        caller_principal_arn="arn:aws:iam::111111111111:role/Notebook",
        broker_secret_arn="arn:aws:secretsmanager:us-east-1:111111111111:secret:broker",
        users=copy.deepcopy(LOCAL_USERS),
    )
    return c


@pytest.fixture
def signed(config, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = f"https://login.microsoftonline.com/{config['tenant_id']}/v2.0"

    def verify(token, *, tenant, audience, version):
        assert version == "2.0"
        return JwtVerifier(
            key=key.public_key(), issuer=issuer, audience=audience, tenant=tenant
        ).verify(token)

    monkeypatch.setattr(client, "verify_entra", verify)

    def mint(label, destination="gateway", **changes):
        claims = {
            "iss": issuer,
            "tid": config["tenant_id"],
            "ver": "2.0",
            "sub": destination + "-" + label,
            "scp": SCOPE,
            "oid": config["users"][label]["oid"],
            "email": config["users"][label]["email"],
            "aud": config["broker_client_id"]
            if destination == "broker"
            else config["gateway_client_id"],
            "azp": config["login_client_id"]
            if destination == "broker"
            else config["broker_client_id"],
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        }
        claims.update(changes)
        return jwt.encode(
            {k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256"
        )

    return mint


def policy(config, claims, arguments, **changes):
    return evaluate(
        claims,
        arguments,
        gateway_arn=LOCAL_GATEWAY,
        tenant=config["tenant_id"],
        broker=config["broker_client_id"],
        users=config["users"],
        **changes,
    )


@pytest.mark.parametrize("label", list(DOMAINS))
def test_four_users_have_only_their_documents_and_d_never_reaches_kb_or_llm(label):
    lab = LocalRagLab()
    row = lab.call(label)
    assert set(row["document_ids"]) == allowed_documents(label)
    assert row["retrieval_calls"] == row["generation_calls"] == (label != "d")
    if label != "d":
        request = lab.kb.calls[0]
        assert request["userContext"]["userId"] == LOCAL_USERS[label]["email"]
        assert request["retrievalConfiguration"] == {
            "managedSearchConfiguration": {"numberOfResults": 10}
        }
        context = json.loads(lab.model.calls[0]["messages"][0]["content"][0]["text"])[
            "trechos_autorizados"
        ]
        assert {c["id"] for c in context} == allowed_documents(label)


@pytest.mark.parametrize("label", list(DOMAINS))
@pytest.mark.parametrize("other", list(DOMAINS))
def test_identity_substitution_cannot_cross_acl_boundaries(label, other):
    lab = LocalRagLab()
    row = lab.call(label, forged_email=LOCAL_USERS[other]["email"])
    expected = label == other and label != "d"
    assert (row["policy"] == "ALLOW") is expected
    assert row["retrieval_calls"] == expected


@pytest.mark.parametrize("claim", ["tid", "oid", "azp", "scp", "email", "ver"])
def test_missing_or_changed_signed_claim_never_authorizes(config, signed, claim):
    identity = client.verify_token(signed("a"), config, destination="gateway")
    args = client.retrieval_arguments(identity, QUESTION)
    assert policy(config, identity.claims, args)
    for changed in (
        {k: v for k, v in identity.claims.items() if k != claim},
        {**identity.claims, claim: "wrong"},
    ):
        assert not policy(config, changed, args)
    assert not policy(config, identity.claims, args, action="rag___AgenticRetrieveStream")
    assert not policy(config, identity.claims, {"retrievalQuery": {"text": "hello"}})


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "wrong"},
        {"exp": 1},
        {"scp": None},
        {"azp": "wrong"},
        {"email": "c@example.invalid"},
    ],
)
def test_verified_jwt_is_required_before_obo_and_query(config, signed, changes):
    with pytest.raises((ValueError, DemoError)):
        client.verify_token(signed("a", **changes), config, destination="gateway")


def test_obo_uses_user_bound_workload_and_verified_destination(config, signed):
    service = botocore.session.get_session().create_client(
        "bedrock-agentcore",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    inbound, outbound = signed("a", "broker"), signed("a")
    env = {"WorkloadName": "rag-broker", "OAuthProviderName": "rag-obo"}
    with Stubber(service) as stub:
        stub.add_response(
            "get_workload_access_token_for_jwt",
            {"workloadAccessToken": "wat"},
            {
                "workloadName": "rag-broker",
                "userToken": inbound,
            },
        )
        stub.add_response(
            "get_resource_oauth2_token",
            {"accessToken": outbound},
            {
                "workloadIdentityToken": "wat",
                "resourceCredentialProviderName": "rag-obo",
                "scopes": [f"api://{config['gateway_client_id']}/.default"],
                "oauth2Flow": "ON_BEHALF_OF_TOKEN_EXCHANGE",
                "customParameters": {"requested_token_use": "on_behalf_of"},
            },
        )
        assert client.exchange(service, config, env, inbound) == outbound
        stub.assert_no_pending_responses()
    bad = MagicMock()
    bad.get_resource_oauth2_token.return_value = {"accessToken": signed("c")}
    with pytest.raises(ValueError, match="IDENTITY_CHANGED"):
        client.exchange(bad, config, env, inbound)
    bad.get_resource_oauth2_token.side_effect = RuntimeError("invalid_grant")
    with pytest.raises(RuntimeError, match="invalid_grant"):
        client.exchange(bad, config, env, inbound)
    assert bad.get_resource_oauth2_token.call_count == 2  # No M2M fallback/retry.


def test_corpus_native_acl_schema_and_no_default_public_documents():
    items = objects("corpus-bucket", LOCAL_USERS)
    global_acl = json.loads(items["acl/global-acl.json"])
    assert len(global_acl) == 2
    for doc in DOCUMENTS:
        metadata = json.loads(items[f"documents/{doc['domain']}/{doc['id']}.txt.metadata.json"])
        acl = {entry["Name"]: entry["Access"] for entry in metadata["accessControlList"]}
        assert acl[LOCAL_USERS["c"]["email"]] == "ALLOW"
        assert acl[LOCAL_USERS["d"]["email"]] == "DENY"
        assert metadata["metadataAttributes"]["document_id"] == doc["id"]
    changed = copy.deepcopy(LOCAL_USERS)
    changed["a"]["email"] = "renamed@example.invalid"
    assert corpus_digest(changed) != corpus_digest(LOCAL_USERS)


def test_empty_results_skip_generation_and_leaked_results_fail_instead_of_postfiltering():
    model = MagicMock()
    assert client.generate_answer(model, "model", QUESTION, [])["generated"] is False
    model.converse.assert_not_called()
    kb = LocalKnowledgeBase()
    mixed = kb.retrieve(userContext={"userId": LOCAL_USERS["c"]["email"]})
    with pytest.raises(ValueError, match="ACL_VIOLATION"):
        client.checked_results(mixed, "a", kb.bucket)
    del mixed["retrievalResults"][0]["metadata"]["domain"]
    with pytest.raises(ValueError, match="ACL_VIOLATION"):
        client.checked_results(mixed, "c", kb.bucket)


def test_managed_source_https_locations_are_validated_against_exact_bucket_and_key():
    kb = LocalKnowledgeBase()
    response = kb.retrieve(userContext={"userId": LOCAL_USERS["a"]["email"]})
    for result in response["retrievalResults"]:
        location = result["location"]["s3Location"]
        location["uri"] = location["uri"].replace(
            f"s3://{kb.bucket}/", f"https://{kb.bucket}.s3.amazonaws.com/"
        )
    assert len(client.checked_results(response, "a", kb.bucket)) == 2
    response["retrievalResults"][0]["location"]["s3Location"]["uri"] += "?other-bucket"
    with pytest.raises(ValueError, match="ACL_VIOLATION"):
        client.checked_results(response, "a", kb.bucket)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["users"]["b"].update(oid=c["users"]["a"]["oid"]),
        lambda c: c["users"]["b"].update(email=c["users"]["a"]["email"]),
        lambda c: c.update(broker_client_id=c["gateway_client_id"]),
        lambda c: c.update(region="sa-east-1"),
        lambda c: c.update(
            broker_secret_arn="arn:aws:secretsmanager:us-west-2:111111111111:secret:x"
        ),
    ],
)
def test_config_rejects_ambiguous_identities_or_wrong_boundaries(config, mutation):
    client.validate_config(config)
    mutation(config)
    with pytest.raises(ValueError):
        client.validate_config(config)


@pytest.mark.parametrize("label", list(DOMAINS))
async def test_real_mcp_protocol_policy_and_rag_roundtrip(config, signed, monkeypatch, label):
    """MCP HTTP ASGI real; JWT/Cedar reais, serviços Knowledge Base e modelo substituídos."""
    kb, model = LocalKnowledgeBase(config["users"]), LocalModel()
    mcp = FastMCP("Local native connector contract", stateless_http=True, json_response=True)

    @mcp.tool(name=TOOL)
    def retrieve(retrievalQuery: dict, userContext: dict, ctx: Context):
        authorization = ctx.request_context.request.headers["authorization"]
        identity = client.verify_token(
            authorization.removeprefix("Bearer "), config, destination="gateway"
        )
        args = {"retrievalQuery": retrievalQuery, "userContext": userContext}
        if not policy(config, identity.claims, args):
            raise ValueError("tool call not allowed")
        return kb.retrieve(knowledgeBaseId="LOCALKB001", **args)

    app = mcp.streamable_http_app()

    @asynccontextmanager
    async def transport(url, token, allowed, **kwargs):
        assert url in allowed
        # Authenticate the token passed by production code, not arguments.
        assert (
            client.verify_token(token, config, destination="gateway").claims["oid"]
            == config["users"][label]["oid"]
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers={"Authorization": "Bearer " + token},
        ) as http:
            async with streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    monkeypatch.setattr(client, "gateway_session", transport)
    env = {
        "GatewayUrl": "https://test.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
        "SourceBucket": kb.bucket,
    }
    async with mcp.session_manager.run():
        row = await client.ask(config, env, signed(label), QUESTION, model)
        assert set(row["document_ids"]) == allowed_documents(label)
        assert len(kb.calls) == len(model.calls) == (label != "d")
        if label == "d":
            assert row["outcome"] == "POLICY_DENY_REPORTED"
        if label == "a":
            spoof = await client.probe_identity_spoof(
                config, env, signed(label), config["users"]["c"]["email"]
            )
            assert spoof["outcome"] == "POLICY_DENY_REPORTED"
            assert len(kb.calls) == 1
        if label != "d":
            coverage = await client.coverage_probe(config, env, signed(label))
            assert set(coverage["coverage_document_ids"]) == allowed_documents(label)
            assert len(kb.calls) == 5


def test_iac_uses_managed_kb_native_acls_and_fixed_connector(tmp_path):
    docs = generate(tmp_path)
    data = docs["data"]["Resources"]
    assert data["KnowledgeBase"]["Properties"]["KnowledgeBaseConfiguration"] == {
        "Type": "MANAGED",
        "ManagedKnowledgeBaseConfiguration": {"EmbeddingModelType": "MANAGED"},
    }
    assert "StorageConfiguration" not in data["KnowledgeBase"]["Properties"]
    cp = data["DataSource"]["Properties"]["DataSourceConfiguration"][
        "ManagedKnowledgeBaseConnectorConfiguration"
    ]["ConnectorParameters"]
    assert cp["aclEnabled"] is True
    assert cp["filterConfiguration"]["inclusionPrefixes"] == ["documents/"]
    assert data["KnowledgeBase"]["DeletionPolicy"] == "RetainExceptOnCreate"
    assert (
        "ChunkingConfiguration"
        not in data["DataSource"]["Properties"]["VectorIngestionConfiguration"]
    )
    assert all(data["SourceBucket"]["Properties"]["PublicAccessBlockConfiguration"].values())
    access = docs["access"]["Resources"]
    target = access["Target"]["Properties"]
    assert target["CredentialProviderConfigurations"] == [
        {"CredentialProviderType": "GATEWAY_IAM_ROLE"}
    ]
    assert target["TargetConfiguration"]["Mcp"]["Connector"]["Enabled"] == ["Retrieve"]
    permissions = access["GatewayRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    assert permissions[0]["Action"] == ["bedrock:GetKnowledgeBase", "bedrock:Retrieve"]
    assert permissions[0]["Resource"] == {"Ref": "KnowledgeBaseArn"}
    assert permissions[1]["Action"] == ["bedrock-agentcore:GetPolicyEngine"]
    assert permissions[1]["Resource"] == {"Fn::GetAtt": ["Engine", "PolicyEngineArn"]}
    engine_access = permissions[2]
    assert set(engine_access["Action"]) == {
        "bedrock-agentcore:AuthorizeAction",
        "bedrock-agentcore:PartiallyAuthorizeActions",
    }
    assert engine_access["Resource"] == [
        {"Fn::GetAtt": ["Engine", "PolicyEngineArn"]},
        {
            "Fn::Sub": "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:"
            "${AWS::AccountId}:gateway/${Project}-*"
        },
    ]
    caller = access["CallerRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    assert any(s["Effect"] == "Deny" and "bedrock:Retrieve" in s["Action"] for s in caller)
    assert "secretsmanager:GetSecretValue" not in json.dumps(caller)
    assert access["Gateway"]["Properties"]["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
    assert (
        access["OAuth"]["Properties"]["Oauth2ProviderConfigInput"]["CustomOauth2ProviderConfig"][
            "OnBehalfOfTokenExchangeConfig"
        ]["GrantType"]
        == "JWT_AUTHORIZATION_GRANT"
    )
    for label in "ABC":
        code = access["AllowUser" + label]["Properties"]["Definition"]["Cedar"]["Statement"][
            "Fn::Sub"
        ]
        assert "context.input.userContext.userId" in code
        assert 'principal.hasTag("email")' in code


def test_current_aws_sdk_accepts_managed_kb_connector_and_acl_retrieve_shapes():
    sdk = botocore.session.get_session()
    validate_parameters(
        {
            "name": "managed-rag",
            "roleArn": "arn:aws:iam::111111111111:role/kb",
            "knowledgeBaseConfiguration": {
                "type": "MANAGED",
                "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"},
            },
        },
        sdk.get_service_model("bedrock-agent").operation_model("CreateKnowledgeBase").input_shape,
    )
    validate_parameters(
        {
            "name": "rag",
            "gatewayIdentifier": "test-gateway",
            "targetConfiguration": {"mcp": {"connector": connector_configuration("LOCALKB001")}},
            "credentialProviderConfigurations": [{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
        },
        sdk.get_service_model("bedrock-agentcore-control")
        .operation_model("CreateGatewayTarget")
        .input_shape,
    )
    validate_parameters(
        {
            "knowledgeBaseId": "LOCALKB001",
            "retrievalQuery": {"text": QUESTION},
            "userContext": {"userId": LOCAL_USERS["a"]["email"]},
            "retrievalConfiguration": {"managedSearchConfiguration": {"numberOfResults": 10}},
        },
        sdk.get_service_model("bedrock-agent-runtime").operation_model("Retrieve").input_shape,
    )


def test_deploy_parameters_match_all_templates_without_cloud_mutation(
    config, tmp_path, monkeypatch
):
    docs = generate(tmp_path / "templates")
    session = MagicMock()
    session.client.return_value.get_caller_identity.return_value = {"Account": config["account_id"]}
    monkeypatch.setattr(
        deployment,
        "outputs",
        lambda *_: {
            "ArtifactBucket": "artifacts",
            "KnowledgeBaseId": "LOCALKB001",
            "KnowledgeBaseArn": "arn:aws:bedrock:us-east-1:111111111111:knowledge-base/LOCALKB001",
        },
    )
    for phase in deployment.PHASES:
        plan = deployment.prepare_phase(tmp_path, config, session, phase)
        params = json.loads(Path(plan["args"][-1]).read_text())
        required = {k for k, v in docs[phase]["Parameters"].items() if "Default" not in v} - {
            "ArtifactKey"
        }
        assert set(params) == required
        assert "--execute" not in plan["args"]
    assert {call[0] for call in session.client.return_value.mock_calls} == {"get_caller_identity"}


def event():
    return {
        "RequestType": "Create",
        "RequestId": "test-request",
        "LogicalResourceId": "Corpus",
        "ResourceProperties": {
            "Bucket": "corpus",
            "KnowledgeBaseId": "LOCALKB001",
            "DataSourceId": "LOCALDS001",
            "Users": LOCAL_USERS,
            "CorpusDigest": corpus_digest(LOCAL_USERS),
        },
    }


def test_corpus_provider_ingests_through_cfn_and_delete_retains():
    s3, kb = MagicMock(), MagicMock()
    kb.get_data_source.return_value = {"dataSource": {"status": "AVAILABLE"}}
    kb.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job"}}
    kb.get_ingestion_job.return_value = {
        "ingestionJob": {"status": "COMPLETE", "statistics": {"numberOfDocumentsFailed": 0}}
    }
    _, result = seed.provision(event(), s3, kb)
    assert result == {"IngestionJobId": "job"}
    assert s3.put_object.call_count == 9
    s3.reset_mock()
    kb.reset_mock()
    assert seed.provision({**event(), "RequestType": "Delete"}, s3, kb)[1] == {"Retained": True}
    s3.assert_not_called()
    assert not s3.mock_calls and not kb.mock_calls


@pytest.mark.parametrize("status", ["FAILED", "STOPPED", "COMPLETE", "IN_PROGRESS"])
def test_ingestion_never_reports_success_for_failed_documents_or_timeout(status):
    s3, kb = MagicMock(), MagicMock()
    kb.get_data_source.return_value = {"dataSource": {"status": "AVAILABLE"}}
    kb.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job"}}
    kb.get_ingestion_job.return_value = {
        "ingestionJob": {"status": status, "statistics": {"numberOfDocumentsFailed": 1}}
    }
    clock = iter([0, 1000])
    with pytest.raises((RuntimeError, TimeoutError)):
        seed.provision(event(), s3, kb, sleep=lambda _: None, monotonic=lambda: next(clock))


def test_no_false_cloud_acceptance_or_sensitive_evidence():
    assert demo()["mode"] == "LOCAL_CONTRACT"
    assert client.acceptance([])["status"] == "PENDING_EVIDENCE"
    rows = []
    for label in DOMAINS:
        rows.append(
            {
                "case": label,
                "mode": "AWS_LIVE",
                "user_ref": label,
                "outcome": "POLICY_DENY_REPORTED" if label == "d" else "RETRIEVED",
                "document_ids": sorted(allowed_documents(label)),
                "coverage_document_ids": sorted(allowed_documents(label)),
                "generated": label != "d",
                "gateway_log_correlation_verified": True,
                "user_bound_workload_token_issued": True,
            }
        )
    rows.append(
        {
            "case": "spoof",
            "mode": "AWS_LIVE",
            "outcome": "POLICY_DENY_REPORTED",
            "gateway_log_correlation_verified": True,
        }
    )
    assert client.acceptance(rows)["status"] == "PASS"
    rows[-1]["outcome"] = "AUTH_OR_EXCHANGE_ERROR"
    assert client.acceptance(rows)["status"] == "PENDING_EVIDENCE"
    rows[0].update(answer="secret text", token="Bearer JWT", email="a@example.invalid")
    assert "secret text" not in json.dumps(client.sanitized_evidence(rows))
    assert "Bearer" not in json.dumps(client.sanitized_evidence(rows))
