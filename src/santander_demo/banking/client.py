"""Preparação IaC e chamadas reais usadas pelo notebook do artigo."""

import hashlib
import json
import re
import shlex
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import boto3
import httpx
import jwt

from santander_demo.banking.spec import DELETE_TOOL, LOBS
from santander_demo.cloud import gateway_session, list_tools, tool_json


def validate_config(config):
    account_keys = {"platform", *LOBS}
    if set(config["accounts"]) != account_keys:
        raise ValueError("FOUR_NAMED_ACCOUNTS_REQUIRED")
    ids = {item["id"] for item in config["accounts"].values()}
    if len(ids) != 4 or any(not re.fullmatch(r"\d{12}", value) for value in ids):
        raise ValueError("FOUR_DISTINCT_ACCOUNTS_REQUIRED")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,20}", config["project"]):
        raise ValueError("INVALID_PROJECT_NAME")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", config["region"]):
        raise ValueError("INVALID_REGION")
    text = json.dumps(config)
    if "REPLACE" in text or any(key in text for key in ['"client_secret"', '"access_token"']):
        raise ValueError("IDENTIFIERS_ONLY_COMPLETE_THE_CONFIG")
    auth = config["auth"]
    if (
        not auth["issuer"].startswith("https://")
        or auth["discovery_url"] != auth["issuer"].rstrip("/") + "/.well-known/openid-configuration"
    ):
        raise ValueError("OIDC_DISCOVERY_MISMATCH")
    if not re.fullmatch(r"[A-Za-z0-9]{10}", config["knowledge_base_id"]):
        raise ValueError("LENDING_KNOWLEDGE_BASE_REQUIRED")
    if not config["model_resource_arns"] or not all(
        value.startswith("arn:aws:bedrock:") for value in config["model_resource_arns"]
    ):
        raise ValueError("MODEL_RESOURCE_ARNS_REQUIRED")
    for item in config["accounts"].values():
        if not item.get("profile"):
            raise ValueError("PROFILE_REQUIRED")
    return config


def load_config(path):
    return validate_config(json.loads(Path(path).read_text()))


def aws_sessions(config):
    """Confere as quatro identidades por STS antes de ler ou preparar um stack."""
    validate_config(config)
    sessions = {}
    for name, account in config["accounts"].items():
        session = boto3.Session(profile_name=account["profile"], region_name=config["region"])
        if session.client("sts").get_caller_identity()["Account"] != account["id"]:
            raise ValueError("PROFILE_ACCOUNT_MISMATCH:" + name)
        sessions[name] = session
    return sessions


def stack_name(config, name):
    return config["project"] + "-" + name


def stack_outputs(session, stack):
    response = session.client("cloudformation").describe_stacks(StackName=stack)
    state = response["Stacks"][0]
    if state["StackStatus"] not in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"}:
        raise RuntimeError("STACK_NOT_READY:" + stack)
    return {item["OutputKey"]: item["OutputValue"] for item in state.get("Outputs", [])}


def runtime_url(region, arn):
    if not re.fullmatch(
        rf"arn:aws:bedrock-agentcore:{re.escape(region)}:\d{{12}}:runtime/[A-Za-z0-9_-]+", arn
    ):
        raise ValueError("INVALID_RUNTIME_ARN")
    return f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{quote(arn, safe='')}/invocations?qualifier=DEFAULT"


def prepare_phase(root, config, sessions, phase):
    """Lê outputs, grava parâmetros sem segredos e retorna comandos; não faz deploy."""
    plans = []
    auth = config["auth"]

    def add(template, account, values):
        path = Path(root) / "config" / f"local.banking-{template}-{account}.json"
        path.write_text(json.dumps(values, indent=2) + "\n")
        args = [
            "uv",
            "run",
            "--extra",
            "banking",
            "python",
            "scripts/banking_deploy.py",
            template,
            "--profile",
            config["accounts"][account]["profile"],
            "--account",
            config["accounts"][account]["id"],
            "--region",
            config["region"],
            "--stack",
            stack_name(config, template),
            "--parameters",
            str(path),
        ]
        plans.append(
            {"template": template, "account": account, "args": args, "command": shlex.join(args)}
        )

    if phase == "bootstrap":
        for account in config["accounts"]:
            add("bootstrap", account, {})
        return plans
    if phase == "platform":
        add(
            "platform",
            "platform",
            {
                "Project": config["project"],
                "DiscoveryUrl": auth["discovery_url"],
                "Audience": auth["audience"],
                "UserClientId": auth["user_client_id"],
                "M2MClientId": auth["m2m_client_id"],
                "M2MSecretArn": auth["m2m_secret_arn"],
            },
        )
        return plans
    platform = stack_outputs(sessions["platform"], stack_name(config, "platform"))

    def bucket(account):
        return stack_outputs(sessions[account], stack_name(config, "bootstrap"))["ArtifactBucket"]

    if phase == "lobs":
        kb = (
            sessions["lending-wealth"]
            .client("bedrock-agent")
            .get_knowledge_base(knowledgeBaseId=config["knowledge_base_id"])["knowledgeBase"]
        )
        if kb["status"] != "ACTIVE":
            raise ValueError("LENDING_KB_NOT_ACTIVE")
        for name in LOBS:
            values = {
                "Project": config["project"],
                "ArtifactBucket": bucket(name),
                "DiscoveryUrl": auth["discovery_url"],
                "Audience": auth["audience"],
                "M2MClientId": auth["m2m_client_id"],
                "GatewayArn": platform["GatewayArn"],
            }
            if name == "lending-wealth":
                values["KnowledgeBaseId"] = config["knowledge_base_id"]
            add(name, name, values)
    elif phase == "bindings":
        values = {
            key: platform[key]
            for key in [
                "GatewayId",
                "GatewayArn",
                "GatewayUrl",
                "PolicyEngineId",
                "OAuthProviderArn",
            ]
        }
        values.update(
            Project=config["project"], ArtifactBucket=bucket("platform"), Scope=auth["scope"]
        )
        for name, spec in LOBS.items():
            arn = stack_outputs(sessions[name], stack_name(config, name))["RuntimeArn"]
            if arn.split(":")[4] != config["accounts"][name]["id"]:
                raise ValueError("LOB_ACCOUNT_MISMATCH")
            values[spec["module"].title() + "Endpoint"] = runtime_url(config["region"], arn)
        add("bindings", "platform", values)
    elif phase == "agent":
        bindings = stack_outputs(sessions["platform"], stack_name(config, "bindings"))
        add(
            "agent",
            "platform",
            {
                "ArtifactBucket": bucket("platform"),
                "DiscoveryUrl": auth["discovery_url"],
                "Audience": auth["audience"],
                "UserClientId": auth["user_client_id"],
                "GatewayUrl": platform["GatewayUrl"],
                "RegistryArn": bindings["RegistryArn"],
                "GuardrailId": platform["GuardrailId"],
                "GuardrailVersion": platform["GuardrailVersion"],
                "ModelId": config["model_id"],
                "ModelResourceArns": ",".join(config["model_resource_arns"]),
            },
        )
    else:
        raise ValueError("UNKNOWN_DEPLOY_PHASE")
    return plans


def preflight(config, sessions):
    """Somente leituras. READY não é evidência de invocação bem-sucedida."""
    from santander_demo.banking.agent import checked_gateway

    platform = stack_outputs(sessions["platform"], stack_name(config, "platform"))
    bindings = stack_outputs(sessions["platform"], stack_name(config, "bindings"))
    agent = stack_outputs(sessions["platform"], stack_name(config, "agent"))
    control = sessions["platform"].client("bedrock-agentcore-control")
    gw = control.get_gateway(gatewayIdentifier=platform["GatewayId"])
    if (
        gw["status"] != "READY"
        or gw["gatewayArn"] != platform["GatewayArn"]
        or gw["gatewayUrl"] != platform["GatewayUrl"]
        or gw["policyEngineConfiguration"]
        != {"arn": platform["PolicyEngineArn"], "mode": "ENFORCE"}
        or gw["authorizerType"] != "CUSTOM_JWT"
    ):
        raise RuntimeError("GATEWAY_NOT_READY_OR_NOT_ENFORCE")
    auth = config["auth"]

    def check_authorizer(authorizer, client):
        required = {
            "inboundTokenClaimName": "cid",
            "inboundTokenClaimValueType": "STRING",
            "authorizingClaimMatchValue": {
                "claimMatchOperator": "EQUALS",
                "claimMatchValue": {"matchValueString": client},
            },
        }
        return (
            authorizer.get("discoveryUrl") == auth["discovery_url"]
            and auth["audience"] in authorizer.get("allowedAudience", [])
            and required in authorizer.get("customClaims", [])
        )

    if not check_authorizer(
        gw["authorizerConfiguration"]["customJWTAuthorizer"], auth["user_client_id"]
    ):
        raise RuntimeError("GATEWAY_AUTHORIZER_MISMATCH")
    checked_gateway(gw["gatewayUrl"], config["region"])
    targets, cursor = [], None
    while True:
        response = control.list_gateway_targets(
            gatewayIdentifier=platform["GatewayId"], **({"nextToken": cursor} if cursor else {})
        )
        targets.extend(response.get("items", []))
        cursor = response.get("nextToken")
        if not cursor:
            break
    if {target["name"] for target in targets} != set(LOBS):
        raise RuntimeError("THREE_LOB_TARGETS_REQUIRED")
    runtime_arns = {}
    for target in targets:
        name = target["name"]
        lob = stack_outputs(sessions[name], stack_name(config, name))
        arn = lob["RuntimeArn"]
        runtime_arns[name] = arn
        if arn.split(":")[4] != config["accounts"][name]["id"]:
            raise ValueError("LOB_ACCOUNT_MISMATCH")
        detail = control.get_gateway_target(
            gatewayIdentifier=platform["GatewayId"], targetId=target["targetId"]
        )
        credentials = detail["credentialProviderConfigurations"]
        if (
            detail["status"] != "READY"
            or detail["targetConfiguration"]["mcp"]["mcpServer"]["endpoint"]
            != runtime_url(config["region"], arn)
            or len(credentials) != 1
            or credentials[0]["credentialProviderType"] != "OAUTH"
        ):
            raise RuntimeError("TARGET_MISMATCH")
        oauth = credentials[0]["credentialProvider"]["oauthCredentialProvider"]
        if (
            oauth.get("grantType") != "CLIENT_CREDENTIALS"
            or oauth["providerArn"] != platform["OAuthProviderArn"]
            or oauth["scopes"] != [auth["scope"]]
        ):
            raise RuntimeError("TARGET_IS_NOT_EXPECTED_M2M")
        runtime = (
            sessions[name]
            .client("bedrock-agentcore-control")
            .get_agent_runtime(agentRuntimeId=lob["RuntimeId"])
        )
        authorizer = runtime["authorizerConfiguration"]["customJWTAuthorizer"]
        hosts = authorizer.get("allowedWorkloadConfiguration", {}).get("hostingEnvironments", [])
        if (
            runtime["status"] != "READY"
            or not check_authorizer(authorizer, auth["m2m_client_id"])
            or {"arn": platform["GatewayArn"]} not in hosts
        ):
            raise RuntimeError("LOB_RUNTIME_AUTHORIZER_MISMATCH")
    registry = control.get_registry(registryId=bindings["RegistryId"])
    if (
        registry["status"] != "READY"
        or registry["approvalConfiguration"]["autoApproval"]
        or registry["authorizerType"] != "AWS_IAM"
    ):
        raise RuntimeError("REGISTRY_NOT_GOVERNED")
    agent_arn = agent["AgentRuntimeArn"]
    if agent_arn.split(":")[4] != config["accounts"]["platform"]["id"]:
        raise ValueError("AGENT_ACCOUNT_MISMATCH")
    hosted = control.get_agent_runtime(agentRuntimeId=agent_arn.rsplit("/", 1)[-1])
    hosted_config = json.loads(hosted.get("environmentVariables", {}).get("BANKING_CONFIG", "{}"))
    if (
        hosted["status"] != "READY"
        or not check_authorizer(
            hosted["authorizerConfiguration"]["customJWTAuthorizer"], auth["user_client_id"]
        )
        or "authorization"
        not in {
            h.lower()
            for h in hosted.get("requestHeaderConfiguration", {}).get("requestHeaderAllowlist", [])
        }
        or hosted_config.get("gateway_url") != gw["gatewayUrl"]
        or hosted_config.get("registry_arn") != bindings["RegistryArn"]
        or hosted_config.get("model_id") != config["model_id"]
    ):
        raise RuntimeError("AGENT_RUNTIME_CONFIGURATION_MISMATCH")
    return {
        "region": config["region"],
        "gateway_url": gw["gatewayUrl"],
        "gateway_id": platform["GatewayId"],
        "registry_arn": bindings["RegistryArn"],
        "agent_runtime_arn": agent["AgentRuntimeArn"],
        "lob_runtime_arns": runtime_arns,
        "guardrail_id": platform["GuardrailId"],
        "guardrail_version": platform["GuardrailVersion"],
        "model_id": config["model_id"],
        "log_group": platform["GatewayLogGroup"],
        "mode": "AWS_READ_ONLY",
        "invocation_verified": False,
    }


def verify_user_token(token, config):
    """JWKS confiável a partir do issuer configurado; o JWT não escolhe a URL."""
    auth = config["auth"]
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.get(auth["discovery_url"])
        response.raise_for_status()
        discovery = response.json()
    if discovery["issuer"] != auth["issuer"]:
        raise ValueError("ISSUER_MISMATCH")
    from urllib.parse import urlsplit

    uri = urlsplit(discovery["jwks_uri"])
    if uri.scheme != "https" or uri.netloc != urlsplit(auth["issuer"]).netloc:
        raise ValueError("JWKS_HOST_MISMATCH")
    key = jwt.PyJWKClient(discovery["jwks_uri"]).get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=auth["audience"],
        issuer=auth["issuer"],
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )
    if claims.get("cid") != auth["user_client_id"] or claims["sub"] != config["expected_user_sub"]:
        raise ValueError("EXPECTED_USER_AND_CLIENT_REQUIRED")
    return {
        "signature": "VERIFIED",
        "audience": "MATCH",
        "user": "EXPECTED",
        "expires_at": claims["exp"],
    }


async def call_tool(environment, token, tool, arguments):
    async with gateway_session(
        environment["gateway_url"], token, {environment["gateway_url"]}
    ) as session:
        names = {t.name for t in await list_tools(session)}
        if tool not in names:
            raise RuntimeError("TOOL_NOT_ADVERTISED")
        result = tool_json(await session.call_tool(tool, arguments))
        # FastMCP encapsula retornos escalares/listas em {"result": ...}.
        for _ in range(3):
            if isinstance(result, dict) and set(result) == {"result"}:
                result = result["result"]
            elif isinstance(result, str):
                result = json.loads(result)
            else:
                break
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError("LOB_BUSINESS_ERROR")
        return result


async def probe_delete(environment, token):
    """Tool original é um stub não destrutivo; erro genérico não comprova Cedar."""
    from mcp.shared.exceptions import McpError

    async with gateway_session(
        environment["gateway_url"], token, {environment["gateway_url"]}
    ) as session:
        try:
            result = await session.call_tool(DELETE_TOOL, {"customer_id": "C003"})
            message = " ".join(block.text for block in result.content if block.type == "text")
            if not result.isError:
                return {
                    "outcome": "NOT_PROVEN",
                    "reason": "Backend respondeu; Policy não comprovada",
                }
        except McpError as exc:
            message = exc.error.message
    return {
        "outcome": "POLICY_DENIAL_REPORTED"
        if "tool call not allowed" in message.lower()
        else "UNCLASSIFIED_ERROR",
        "backend_non_invocation": "REVIEW_GATEWAY_AND_LOB_LOGS",
    }


async def invoke_agent(environment, token, prompt):
    url = runtime_url(environment["region"], environment["agent_runtime_arn"])
    async with httpx.AsyncClient(timeout=240, follow_redirects=False) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": "Bearer " + token,
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": uuid4().hex + uuid4().hex,
            },
            json={"prompt": prompt},
        )
    if response.status_code != 200:
        raise RuntimeError(f"AGENT_HTTP_{response.status_code}")
    result = response.json()
    if isinstance(result, str):
        result = json.loads(result)
    if result.get("mode") != "AWS_LIVE":
        raise RuntimeError("AGENT_DID_NOT_COMPLETE")
    return result


def sanitized_evidence(environment, result, denial):
    observed = sorted(
        {
            item["lob"]
            for item in result.get("tool_calls", [])
            if item["status"] == "success" and item["lob"] in LOBS
        }
    )
    return {
        "mode": "AWS_LIVE",
        "lob_accounts": len(environment["lob_runtime_arns"]),
        "lobs_with_successful_tool_results": observed,
        "three_lobs_observed": set(observed) == set(LOBS),
        "response_sha256": hashlib.sha256(result["response"].encode()).hexdigest(),
        "policy_probe": denial,
        "trace": result.get("tool_calls", []),
        "downstream_human_identity": "NOT_PROPAGATED_M2M",
        "data_residency_and_backend_logs": "REVIEW_REQUIRED",
    }
