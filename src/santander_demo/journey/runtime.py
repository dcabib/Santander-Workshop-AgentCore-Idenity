"""Agente determinístico hospedado: valida, descobre, delega e consulta via MCP.

Não há provisionamento, SQL livre, identidade recebida como argumento ou fallback M2M.
O modo determinístico torna a prova de segurança repetível; o lab 11 mantém Strands.
"""

import asyncio
import json
import logging
import os
from datetime import timedelta
from uuid import UUID

import boto3
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import Context, FastMCP
from mcp.shared.exceptions import McpError

from santander_demo.banking.agent import checked_gateway
from santander_demo.identity import verify_entra
from santander_demo.journey.evidence import classify_error, fingerprint, statement_evidence
from santander_demo.journey.spec import AGENTS, IDENTITY_QUERY, SCOPE, canary_query, tool_name

logger = logging.getLogger("santander.journey")


def verified_identity(token, config, *, hub=False):
    identity = verify_entra(
        token,
        tenant=config["tenant"],
        audience=config["hub_audience"] if hub else config["audience"],
        version="2.0",
    )
    c = identity.claims
    caller = config["audience"] if hub else config["caller"]
    if c.get("azp") != caller or c.get("ver") != "2.0" or c.get("scp") != SCOPE or not c.get("oid"):
        raise ValueError("DELEGATION_MISMATCH")
    principal = c.get(config["subject_claim"])
    if not isinstance(principal, str) or not principal:
        raise ValueError("FEDERATED_SUBJECT_CLAIM_MISSING")
    return identity


def delegated_token(client, config, user_token):
    """AgentCore Identity, com workload criado pelo CloudFormation."""
    workload = client.get_workload_access_token_for_jwt(
        workloadName=config["workload_name"],
        userToken=user_token,
    )
    response = client.get_resource_oauth2_token(
        workloadIdentityToken=workload["workloadAccessToken"],
        resourceCredentialProviderName=config["provider_name"],
        scopes=[f"api://{config['hub_audience']}/.default"],
        oauth2Flow="ON_BEHALF_OF_TOKEN_EXCHANGE",
        customParameters={"requested_token_use": "on_behalf_of"},
    )
    if not response.get("accessToken"):
        raise RuntimeError("IDENTITY_EXCHANGE_NO_TOKEN")
    return response["accessToken"]


def validate_record(record, config, capability):
    if record.get("status") != "APPROVED" or record.get("registryArn") != config["registry_arn"]:
        return False
    descriptor = record.get("descriptors", {}).get("mcp", {})
    if not descriptor:
        return False
    server = json.loads(descriptor["server"]["inlineContent"])
    if server.get("name") != "com.santander.demo/" + capability:
        return False
    if (
        server.get("version") != "1.0.0"
        or server.get("_meta", {}).get("com.santander/owner") != "dados"
        or server.get("_meta", {}).get("com.santander/instance") != config["project"]
        or server.get("remotes") != [{"type": "streamable-http", "url": config["hub_url"]}]
    ):
        raise ValueError("REGISTRY_CONTRACT_MISMATCH")
    tools = json.loads(descriptor["tools"]["inlineContent"])["tools"]
    if {t["name"] for t in tools} != {tool_name(capability)}:
        raise ValueError("REGISTRY_TOOLS_MISMATCH")
    return True


def discover(session, config, capability):
    """Consumo cross-account por role somente de leitura; aprovação não concede execução."""
    credentials = session.client("sts").assume_role(
        RoleArn=config["registry_role_arn"],
        RoleSessionName="santander-discovery",
    )["Credentials"]
    client = boto3.client(
        "bedrock-agentcore",
        region_name=config["region"],
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )
    cursor, seen = None, set()
    while True:
        response = client.search_registry_records(
            registryIds=[config["registry_arn"]],
            searchQuery="santander " + capability,
            maxResults=100,
            **({"nextToken": cursor} if cursor else {}),
        )
        if any(
            validate_record(record, config, capability)
            for record in response.get("registryRecords", [])
        ):
            return {
                "status": "APPROVED",
                "owner": "dados",
                "version": "1.0.0",
                "instance": config["project"],
            }
        cursor = response.get("nextToken")
        if not cursor:
            raise RuntimeError("APPROVED_CAPABILITY_NOT_FOUND")
        if cursor in seen:
            raise RuntimeError("REGISTRY_PAGINATION_LOOP")
        seen.add(cursor)


async def consult(config, token, capability, request_id, *, session=None):
    if capability not in AGENTS:
        raise ValueError("UNKNOWN_CAPABILITY")
    request_id = str(UUID(request_id))
    checked_gateway(config["hub_url"], config["region"])
    identity = verified_identity(token, config)
    session = session or boto3.Session(region_name=config["region"])
    registry = await asyncio.to_thread(discover, session, config, capability)
    hub_token = await asyncio.to_thread(
        delegated_token,
        session.client("bedrock-agentcore"),
        config,
        token,
    )
    delegated = verified_identity(hub_token, config, hub=True)
    if (
        delegated.claims["oid"] != identity.claims["oid"]
        or delegated.claims[config["subject_claim"]].casefold()
        != identity.claims[config["subject_claim"]].casefold()
    ):
        raise ValueError("IDENTITY_CHANGED_DURING_OBO")
    expected = identity.claims[config["subject_claim"]]
    query = canary_query(config["tables"][capability])
    report = {
        "mode": "AWS_LIVE",
        "request_id": request_id,
        "agent": config["agent"],
        "agent_location": "ORIGIN_ACCOUNT_RUNTIME",
        "tool": tool_name(capability),
        "user_ref": identity.summary()["user_ref"],
        "registry": registry,
        "identity_verified": False,
        "query_id": None,
        "query_sha256": fingerprint(query),
        "hub_gateway_request_ids": [],
        "gateway_log_correlation_verified": False,
        "backend_non_execution_verified": False,
    }

    async def capture(response):
        value = response.headers.get("x-amzn-requestid")
        if value and value not in report["hub_gateway_request_ids"]:
            report["hub_gateway_request_ids"].append(value)

    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + hub_token},
        follow_redirects=False,
        timeout=httpx.Timeout(240, connect=15),
        event_hooks={"response": [capture]},
    ) as http:
        async with streamable_http_client(
            config["hub_url"],
            http_client=http,
            terminate_on_close=False,
        ) as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=240)
            ) as mcp:
                await mcp.initialize()
                for stage, statement in (("identity", IDENTITY_QUERY), ("canary", query)):
                    try:
                        result = await mcp.call_tool(
                            tool_name(capability),
                            {"query": statement},
                            meta={"com.santander/request_id": request_id},
                        )
                        proof = statement_evidence(result, expected)
                    except McpError as exc:
                        proof = {"outcome": classify_error(exc.error.message), "query_id": None}
                    report["outcome"] = proof["outcome"]
                    report[stage + "_query_id"] = proof.get("query_id")
                    if stage == "identity":
                        report["identity_verified"] = proof["outcome"] == "PER_USER_VERIFIED"
                    else:
                        report["query_id"] = proof.get("query_id")
                    if proof["outcome"] != "PER_USER_VERIFIED":
                        break
    # Evidência operacional, sem bearer, e-mail, SQL completo ou linhas de dados.
    logger.info(json.dumps({"event": "santander_journey", **report}))
    return report


def create_server(config=None):
    config = config or json.loads(os.environ["JOURNEY_CONFIG"])
    mcp = FastMCP("Santander " + config["agent"], host="0.0.0.0", port=8000, stateless_http=True)

    @mcp.tool()
    async def consultar(capacidade: str, request_id: str, ctx: Context) -> dict:
        """Consulta uma capacidade do catálogo com a identidade real do chamador."""
        request = ctx.request_context.request
        authorization = request.headers.get("authorization", "") if request else ""
        if not authorization.startswith("Bearer "):
            raise ValueError("USER_BEARER_REQUIRED")
        return await consult(config, authorization[7:], capacidade, request_id)

    return mcp
