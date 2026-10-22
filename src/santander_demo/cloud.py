"""Clientes de leitura/invocação. Provisionamento pertence exclusivamente a infra/."""

import json
from contextlib import asynccontextmanager
from datetime import timedelta

import boto3
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from santander_demo.config import Environment
from santander_demo.contracts import CLIENTE, TOOLS, DemoError
from santander_demo.identity import verify_entra
from santander_demo.registry import checked_endpoint


@asynccontextmanager
async def gateway_session(url: str, token: str, allowed: set[str], *, timeout_seconds=90):
    checked_endpoint(url, allowed)
    # Não seguir redirecionamentos: o bearer só sai para o endpoint aprovado.
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_seconds, connect=15),
    ) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=timeout_seconds)
            ) as session:
                await session.initialize()
                yield session


async def list_tools(session):
    tools, cursor = [], None
    seen = set()
    while True:
        page = await session.list_tools(cursor=cursor)
        tools.extend(page.tools)
        cursor = page.nextCursor
        if cursor is None:
            return tools
        if cursor in seen:
            raise DemoError("MCP_PAGINATION_LOOP")
        seen.add(cursor)


def tool_json(result):
    if result.isError:
        # Não rotular qualquer erro como Policy: a classificação depende da evidência AWS.
        message = " ".join(c.text for c in result.content if c.type == "text").lower()
        if "tool call not allowed" in message:
            raise DemoError("POLICY_DENIAL_REPORTED")
        raise DemoError("MCP_TOOL_ERROR")
    if result.structuredContent is not None:
        return result.structuredContent
    for block in result.content:
        if block.type == "text":
            try:
                return json.loads(block.text)
            except ValueError:
                continue
    raise DemoError("MCP_RESULT_NOT_JSON")


class CloudWorkshop:
    def __init__(self, config: Environment, session=None):
        self.config = config
        self.session = session or boto3.Session(
            profile_name=config.profile, region_name=config.region
        )
        self.control = self.session.client("bedrock-agentcore-control")

    def preflight(self):
        """Read-only; não imprime credenciais nem tenta corrigir recursos."""
        c = self.config
        caller = self.session.client("sts").get_caller_identity()
        gateway = self.control.get_gateway(gatewayIdentifier=c.gateway_id)
        assert gateway["gatewayArn"] == c.gateway_arn, "Gateway diferente do manifesto"
        assert gateway["gatewayUrl"] == c.gateway_url, "Endpoint diferente do manifesto"
        assert gateway["status"] == "READY"
        policy = self.control.get_policy_engine(policyEngineId=c.policy_engine_id)
        assert gateway["policyEngineConfiguration"] == {
            "arn": policy["policyEngineArn"],
            "mode": "ENFORCE",
        }
        assert gateway["authorizerType"] == "CUSTOM_JWT"
        authorizer = gateway["authorizerConfiguration"]["customJWTAuthorizer"]
        assert c.gateway_audience in authorizer["allowedAudience"]
        discovery = f"https://login.microsoftonline.com/{c.tenant_id}/"
        discovery += "v2.0/" if c.token_version == "2.0" else ""
        assert authorizer["discoveryUrl"] == discovery + ".well-known/openid-configuration"
        registry = self.control.get_registry(registryId=c.registry_id)
        assert registry["registryArn"] == c.registry_arn
        assert registry["status"] == "READY"
        assert registry["authorizerType"] == "AWS_IAM"
        assert registry["approvalConfiguration"]["autoApproval"] is False
        return {
            "mode": "AWS_READ_ONLY",
            "caller_account": caller["Account"],
            "gateway": gateway["status"],
            "policy": "ENFORCE",
            "registry": registry["status"],
            "user_obo_verified": False,
        }

    def verify_token(self, token):
        c = self.config
        return verify_entra(
            token, tenant=c.tenant_id, audience=c.gateway_audience, version=c.token_version
        )

    def search(self, query: str):
        c = self.config
        assumed = self.session.client("sts").assume_role(
            RoleArn=c.registry_consumer_role_arn, RoleSessionName="santander-discovery"
        )["Credentials"]
        client = boto3.client(
            "bedrock-agentcore",
            region_name=c.region,
            aws_access_key_id=assumed["AccessKeyId"],
            aws_secret_access_key=assumed["SecretAccessKey"],
            aws_session_token=assumed["SessionToken"],
        )
        response = client.search_registry_records(
            registryIds=[c.registry_arn], searchQuery=query, maxResults=20
        )
        return [
            r
            for r in response.get("registryRecords", [])
            if r["status"] == "APPROVED" and r["registryArn"] == c.registry_arn
        ]

    def registry_states(self):
        records, token = [], None
        while True:
            args = {"registryId": self.config.registry_id, "maxResults": 100}
            if token:
                args["nextToken"] = token
            page = self.control.list_registry_records(**args)
            records.extend(
                {"name": r["name"], "status": r["status"]} for r in page["registryRecords"]
            )
            token = page.get("nextToken")
            if not token:
                return records

    def policy_draft(self, generation_id: str):
        args = {"policyEngineId": self.config.policy_engine_id, "policyGenerationId": generation_id}
        generation = self.control.get_policy_generation(**args)
        if generation["status"] != "GENERATED":
            raise DemoError("POLICY_DRAFT_NOT_READY")
        assets, cursor = [], None
        while True:
            page = self.control.list_policy_generation_assets(
                **args, **({"nextToken": cursor} if cursor else {})
            )
            assets.extend(page["policyGenerationAssets"])
            cursor = page.get("nextToken")
            if not cursor:
                break
        return {"mode": "AWS_LIVE", "assets": assets, "review_required": True, "published": False}

    async def call(self, token, tool, arguments):
        self.verify_token(token)
        c = self.config
        async with gateway_session(c.gateway_url, token, {c.gateway_url}) as session:
            advertised = {t.name for t in await list_tools(session)}
            if tool not in advertised:
                raise DemoError("TOOL_NOT_ADVERTISED")
            try:
                return tool_json(await session.call_tool(tool, arguments))
            except McpError as exc:
                if "tool call not allowed" in exc.error.message.lower():
                    raise DemoError("POLICY_DENIAL_REPORTED") from None
                raise DemoError("MCP_PROTOCOL_ERROR") from None

    async def graph_me(self, token):
        identity = self.verify_token(token)
        assert identity.claims.get("oid") == self.config.expected_graph_oid
        profile = await self.call(token, self.config.graph_tool, {})
        # O profile é processado em memória. O notebook só recebe um booleano.
        assert profile.get("id") == self.config.expected_graph_oid, "OBO devolveu outro principal"
        return {"mode": "AWS_LIVE", "graph_user_matches": True, **identity.summary()}

    async def analyze(self, token, cliente_id=CLIENTE):
        self.verify_token(token)
        c = self.config
        results, invoked = [], set()
        for query in ("risco crédito cliente", "indícios fraude cliente"):
            for record in self.search(query):
                mcp = record["descriptors"].get("mcp")
                if not mcp:
                    continue
                server = json.loads(mcp["server"]["inlineContent"])
                for remote in server.get("remotes", []):
                    checked_endpoint(remote["url"], {c.gateway_url})
                if not server.get("remotes"):
                    raise DemoError("REGISTRY_ENDPOINT_MISSING")
                descriptors = json.loads(mcp["tools"]["inlineContent"])["tools"]
                for tool in descriptors:
                    name = tool["name"]
                    if name not in TOOLS or name in invoked:
                        continue
                    invoked.add(name)
                    try:
                        result = await self.call(
                            token,
                            name,
                            {
                                "cliente_id": cliente_id,
                                "max_registros": 10,
                            },
                        )
                        results.append({"tool": name, "result": result})
                    except DemoError as exc:
                        results.append({"tool": name, "error": exc.code})
        if not invoked:
            raise DemoError("REGISTRY_NO_APPROVED_CAPABILITY")
        return {"mode": "AWS_LIVE", "results": results}


def login_device(config: Environment):
    """Interativo, sem arquivo de token e sem client secret; sujeito à política do tenant."""
    import msal

    app = msal.PublicClientApplication(
        config.login_client_id,
        authority=f"https://login.microsoftonline.com/{config.tenant_id}",
    )
    flow = app.initiate_device_flow(scopes=[config.login_scope])
    if "user_code" not in flow:
        raise DemoError("ENTRA_DEVICE_FLOW_UNAVAILABLE")
    # Só a instrução de login; não exibir o objeto flow ou o resultado MSAL.
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise DemoError("ENTRA_LOGIN_FAILED")
    return result["access_token"]


def login_confidential_agent(config: Environment):
    """Login humano → OBO do agente confidencial → token destinado ao Gateway.

    O segredo é lido do Secrets Manager pelo instrutor e mantido somente em memória.
    Essa primeira troca MSAL é distinta do OBO gerenciado no AgentCore Gateway.
    """
    import msal

    if not all((config.agent_client_id, config.agent_secret_arn, config.gateway_obo_scope)):
        raise DemoError("CONFIDENTIAL_AGENT_CONFIG_REQUIRED")
    user_assertion = login_device(config)
    session = boto3.Session(profile_name=config.profile, region_name=config.region)
    secret_response = session.client("secretsmanager").get_secret_value(
        SecretId=config.agent_secret_arn
    )
    client_secret = json.loads(secret_response["SecretString"])["client_secret"]
    app = msal.ConfidentialClientApplication(
        config.agent_client_id,
        authority=f"https://login.microsoftonline.com/{config.tenant_id}",
        client_credential=client_secret,
    )
    result = app.acquire_token_on_behalf_of(
        user_assertion=user_assertion, scopes=[config.gateway_obo_scope]
    )
    if "access_token" not in result:
        raise DemoError("CONFIDENTIAL_AGENT_OBO_FAILED")
    token = result["access_token"]
    identity = verify_entra(
        token,
        tenant=config.tenant_id,
        audience=config.gateway_audience,
        version=config.token_version,
    )
    caller = identity.claims.get("azp", identity.claims.get("appid"))
    if caller != config.agent_client_id:
        raise DemoError("CONFIDENTIAL_AGENT_CALLER_MISMATCH")
    return token
