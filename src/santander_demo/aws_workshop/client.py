"""Cliente dos ambientes implantados; nenhuma implementação de serviços em memória."""

import json
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import McpError

from santander_demo.aws_endpoints import gateway_region

from .config import check_accounts, load, session, stack_outputs
from .contracts import USER_TOKEN_HEADER
from .identity import login, verify


def stack_name(config, domain, phase):
    suffix = "core" if domain == "platform" else domain.split("-")[0]
    return f"{config['project']}-{suffix}-{phase}"


def verify_target_headers(headers):
    # GetGatewayTarget acrescenta este header reservado quando Policy está
    # habilitada. Ele não substitui o header de identidade nem autoriza a fonte.
    normalized = {header.lower() for header in headers}
    required = {USER_TOKEN_HEADER.lower()}
    service_header = "x-amzn-bedrock-agentcore-policy-session-id"
    if len(normalized) != len(headers) or normalized not in (required, required | {service_header}):
        raise RuntimeError("UNEXPECTED_TARGET_HEADER_ALLOWLIST")


@asynccontextmanager
async def gateway_session(url, token, *, request_ids=None):
    try:
        gateway_region(url)
    except ValueError as exc:
        raise ValueError("UNTRUSTED_GATEWAY_URL") from exc

    async def capture(response):
        try:
            request = json.loads(response.request.content)
        except (ValueError, RuntimeError):
            return
        value = response.headers.get("x-amzn-requestid")
        if (
            request.get("method") == "tools/call"
            and value and request_ids is not None and value not in request_ids
        ):
            request_ids.append(value)

    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token},
        timeout=httpx.Timeout(180, connect=15), follow_redirects=False,
        event_hooks={"response": [capture]},
    ) as http:
        async with streamable_http_client(
            url, http_client=http, terminate_on_close=False,
        ) as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=180),
            ) as mcp:
                await mcp.initialize()
                yield mcp


def content(result):
    if result.isError:
        raise RuntimeError("MCP_TOOL_ERROR:" + " ".join(
            x.text for x in result.content if x.type == "text"
        )[:500])
    if result.structuredContent is not None:
        return result.structuredContent
    values = [json.loads(x.text) for x in result.content if x.type == "text"]
    if len(values) != 1:
        raise ValueError("EXPECTED_ONE_TOOL_RESULT")
    return values[0]


def denial_kind(text):
    text = text.lower()
    if "source_permission_denied" in text or "source_application_denied" in text:
        return "SOURCE_DENY"
    if ("policy" in text and any(x in text for x in ["denied", "not allowed", "unauthorized", "deny"])):
        return "POLICY_DENY"
    return None


class AWSWorkshop:
    def __init__(self, config_path, domain="platform"):
        self.config = load(config_path)
        self.domain = domain
        self.accounts = check_accounts(
            self.config, domains=tuple(dict.fromkeys(["platform", domain])),
        )
        self.aws = session(self.config, domain)
        self.platform = session(self.config, "platform")
        self.identity = self.outputs("identity", domain="platform")
        self.gateway = self.outputs("gateway")
        self.backend = self.outputs("backend")
        self.bindings = self.outputs("bindings")

    def outputs(self, phase, *, domain=None):
        domain = domain or self.domain
        aws = self.platform if domain == "platform" else self.aws
        return stack_outputs(aws, stack_name(self.config, domain, phase))

    def login(self, user="c", application="supervisor"):
        return login(self.platform, self.identity, user, application)

    def claims(self, token):
        return verify(token, {
            "issuer": self.identity["Issuer"],
            "clients": [self.identity["SupervisorClientId"], self.identity["RiscosClientId"]],
        })

    def preflight(self):
        control = self.aws.client("bedrock-agentcore-control")
        gateway = control.get_gateway(gatewayIdentifier=self.gateway["GatewayId"])
        runtime = control.get_agent_runtime(agentRuntimeId=self.backend["RuntimeId"])
        memory = control.get_memory(memoryId=self.backend["MemoryId"])["memory"]
        if gateway["status"] != "READY" or runtime["status"] != "READY" or memory["status"] != "ACTIVE":
            raise RuntimeError("AWS_COMPONENT_NOT_READY")
        if gateway.get("authorizerType") != "CUSTOM_JWT":
            raise RuntimeError("GATEWAY_COGNITO_AUTH_REQUIRED")
        from .runtime_boundary import policy

        if runtime.get("authorizerConfiguration") or runtime.get("requestHeaderConfiguration") != {
            "requestHeaderAllowlist": [USER_TOKEN_HEADER],
        }:
            raise RuntimeError("RUNTIME_SIGV4_AND_USER_JWT_REQUIRED")
        boundary = json.loads(control.get_resource_policy(resourceArn=self.backend["RuntimeArn"])["policy"])
        if boundary != policy(self.backend["RuntimeArn"], self.gateway["GatewayRoleArn"]):
            raise RuntimeError("RUNTIME_GATEWAY_ROLE_BOUNDARY_REQUIRED")
        role = self.aws.client("iam").get_role(RoleName=self.gateway["GatewayRoleName"])["Role"]
        trust = role["AssumeRolePolicyDocument"]["Statement"]
        if len(trust) != 1 or trust[0].get("Condition") != {
            "StringEquals": {"aws:SourceAccount": self.config["accounts"][self.domain]["id"]},
            "ArnLike": {"aws:SourceArn": self.gateway["GatewayArn"]},
        } or trust[0].get("Principal") != {"Service": "bedrock-agentcore.amazonaws.com"}:
            raise RuntimeError("EXACT_GATEWAY_ROLE_TRUST_REQUIRED")
        auth = gateway["authorizerConfiguration"]["customJWTAuthorizer"]
        if (
            auth["discoveryUrl"] != self.identity["Issuer"] + "/.well-known/openid-configuration"
            or set(auth["allowedAudience"]) != {
                self.identity["SupervisorClientId"], self.identity["RiscosClientId"],
            }
        ):
            raise RuntimeError("GATEWAY_IDENTITY_CONFIG_MISMATCH")
        if gateway["policyEngineConfiguration"] != {
            "arn": self.gateway["PolicyEngineArn"], "mode": "ENFORCE",
        }:
            raise RuntimeError("POLICY_MUST_ENFORCE")
        if self.gateway.get("PropagationMode") != "SIGV4_WITH_VERIFIED_USER_JWT" or gateway.get(
            "interceptorConfigurations"
        ) != [{
            "interceptionPoints": ["REQUEST"],
            "interceptor": {"lambda": {"arn": self.gateway["InterceptorArn"]}},
            "inputConfiguration": {"passRequestHeaders": True},
        }]:
            raise RuntimeError("VERIFIED_JWT_INTERCEPTOR_REQUIRED")
        target = control.get_gateway_target(
            gatewayIdentifier=self.gateway["GatewayId"], targetId=self.bindings["TargetId"],
        )
        if target["status"] != "READY" or target.get("credentialProviderConfigurations") != [{
            "credentialProviderType": "GATEWAY_IAM_ROLE", "credentialProvider": {
                "iamCredentialProvider": {"service": "bedrock-agentcore", "region": self.config["region"]},
            },
        }]:
            raise RuntimeError("SIGV4_TARGET_NOT_READY")
        verify_target_headers(target.get("metadataConfiguration", {}).get("allowedRequestHeaders", []))
        return {
            "execution": "AWS", "accounts": self.accounts, "gateway": gateway["status"],
            "runtime": runtime["status"], "memory": memory["status"], "policy": "ENFORCE",
            "source_kind": self.backend["SourceKind"],
            "runtime_ingress": "GATEWAY_ROLE_ONLY",
        }

    def deny_direct_runtime(self):
        """Invocação IAM sem usar a role do Gateway deve ser negada pelo serviço."""
        from botocore.exceptions import ClientError

        try:
            self.aws.client("bedrock-agentcore").invoke_agent_runtime(
                agentRuntimeArn=self.backend["RuntimeArn"], runtimeSessionId=str(uuid.uuid4()),
                payload=json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "direct-denial-check", "version": "1"}},
                }).encode(),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "AccessDeniedException":
                raise
            native_id = exc.response["ResponseMetadata"]["RequestId"]
            return {"direct_runtime": "IAM_DENY", "runtime_request_id": native_id}
        raise AssertionError("DIRECT_RUNTIME_BYPASS")

    async def tools(self, token):
        result, seen = [], set()
        async with gateway_session(self.gateway["GatewayUrl"], token) as mcp:
            cursor = None
            while True:
                page = await mcp.list_tools(cursor=cursor)
                result.extend(x.model_dump() for x in page.tools)
                if not page.nextCursor:
                    break
                if page.nextCursor in seen:
                    raise ValueError("MCP_REPEATED_CURSOR")
                seen.add(page.nextCursor)
                cursor = page.nextCursor
        return result

    async def call(self, token, tool, arguments, *, request_id=None):
        correlation = request_id or str(uuid.uuid4())
        requests = []
        async with gateway_session(
            self.gateway["GatewayUrl"], token, request_ids=requests,
        ) as mcp:
            result = await mcp.call_tool(tool, {**arguments, "request_id": correlation})
        if not requests:
            raise AssertionError("GATEWAY_REQUEST_ID_MISSING")
        return {"request_id": correlation, "gateway_request_ids": requests, "result": content(result)}

    async def expect_denial(self, token, tool, arguments, expected="POLICY_DENY"):
        correlation, requests = str(uuid.uuid4()), []
        async with gateway_session(self.gateway["GatewayUrl"], token, request_ids=requests) as mcp:
            try:
                result = await mcp.call_tool(tool, {**arguments, "request_id": correlation})
            except McpError as exc:
                kind = denial_kind(exc.error.message)
            else:
                if not result.isError:
                    raise AssertionError("UNEXPECTED_TOOL_AUTHORIZATION")
                kind = denial_kind(" ".join(x.text for x in result.content if x.type == "text"))
        if kind != expected:
            raise AssertionError(f"EXPECTED_{expected}_GOT_{kind}")
        if not requests:
            raise AssertionError("GATEWAY_REQUEST_ID_MISSING")
        return {"outcome": kind, "request_id": correlation, "gateway_request_ids": requests}

    async def invoke_agent(self, token, question, *, domain="platform", phase="agent"):
        from urllib.parse import quote

        if phase not in {"agent", "agent-riscos", "agent-fraude"}:
            raise ValueError("UNKNOWN_AGENT_PHASE")
        environment = self.outputs(phase)
        url = (
            f"https://bedrock-agentcore.{self.config['region']}.amazonaws.com/runtimes/"
            + quote(environment["RuntimeArn"], safe="") + "/invocations?qualifier=DEFAULT"
        )
        async with httpx.AsyncClient(follow_redirects=False, timeout=240) as http:
            response = await http.post(url, headers={
                "Authorization": "Bearer " + token,
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": str(uuid.uuid4()),
            }, json={"question": question, "domain": domain})
        response.raise_for_status()
        result = response.json()
        if result.get("execution") != "AWS_AGENTCORE_RUNTIME" or not result.get("tool_calls"):
            raise AssertionError("AGENT_EVIDENCE_MISSING")
        return result

    async def deny_anonymous(self):
        async with httpx.AsyncClient(follow_redirects=False, timeout=30) as http:
            result = await http.post(self.gateway["GatewayUrl"], json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "anonymous-check", "version": "1"}},
            })
        if result.status_code not in {401, 403}:
            raise AssertionError(f"ANONYMOUS_NOT_DENIED:{result.status_code}")
        native_id = result.headers.get("x-amzn-requestid")
        if not native_id:
            raise AssertionError("GATEWAY_REQUEST_ID_MISSING")
        return {"anonymous_status": result.status_code, "gateway_request_id": native_id}
