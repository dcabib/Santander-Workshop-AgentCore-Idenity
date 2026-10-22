"""Preparação IaC por fases e ensaio com dois usuários; nenhum provisionamento por SDK."""

import json
import re
import shlex
from pathlib import Path
from uuid import UUID, uuid4

import boto3

from santander_demo.banking.agent import checked_gateway
from santander_demo.banking.client import runtime_url, stack_outputs
from santander_demo.cloud import gateway_session, tool_json
from santander_demo.federation.client import pages
from santander_demo.identity import verify_entra
from santander_demo.journey.spec import ACCOUNTS, AGENTS, SCOPE, canary_query, cedar

PHASES = (
    "bootstrap",
    "gateways",
    "data-bindings",
    "platform-bindings",
    "registry",
    "agents",
    "origin-bindings",
    "approve-registry",
)


def validate_config(config):
    if "REPLACE" in json.dumps(config) or any(
        key in json.dumps(config) for key in ('"access_token"', '"client_secret"')
    ):
        raise ValueError("COMPLETE_IDENTIFIERS_ONLY_NO_SECRETS")
    if set(config["accounts"]) != set(ACCOUNTS) or set(config["agents"]) != set(AGENTS):
        raise ValueError("THREE_ACCOUNTS_TWO_AGENTS_REQUIRED")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,25}", config["project"]):
        raise ValueError("INVALID_PROJECT")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", config["region"]):
        raise ValueError("INVALID_REGION")
    ids = [account["id"] for account in config["accounts"].values()]
    if len(set(ids)) != 3 or any(not re.fullmatch(r"\d{12}", value) for value in ids):
        raise ValueError("THREE_DISTINCT_ACCOUNTS_REQUIRED")
    UUID(config["tenant_id"])
    applications = [config["login_client_id"]] + [
        a["gateway_client_id"] for a in config["accounts"].values()
    ]
    applications += [a["client_id"] for a in config["agents"].values()]
    if len({str(UUID(value)) for value in applications}) != 6:
        raise ValueError("SIX_DISTINCT_ENTRA_APPS_REQUIRED")
    if (
        set(config["users"]) != {"a", "b"}
        or len({str(UUID(value)) for value in config["users"].values()}) != 2
    ):
        raise ValueError("TWO_DISTINCT_USERS_REQUIRED")
    secrets = [
        (name, config["accounts"][name]["gateway_secret_arn"]) for name in ("origin", "platform")
    ] + [("origin", config["agents"][agent]["secret_arn"]) for agent in AGENTS]
    db = config["databricks"]
    secrets.append(("data", db["secret_arn"]))
    for account, arn in secrets:
        prefix = (
            f"arn:aws:secretsmanager:{config['region']}:{config['accounts'][account]['id']}:secret:"
        )
        if not arn.startswith(prefix) or not arn[len(prefix) :]:
            raise ValueError("SECRET_ACCOUNT_REGION_MISMATCH")
    if any(not account["profile"] for account in config["accounts"].values()):
        raise ValueError("PROFILE_REQUIRED")
    if not re.fullmatch(r"https://adb-[0-9]+\.[0-9]+\.azuredatabricks\.net", db["host"]):
        raise ValueError("EXACT_AZURE_DATABRICKS_HOST_REQUIRED")
    endpoint, scopes = {
        "legacy_sql": (db["host"] + "/api/2.0/mcp/sql", {"all-apis", "sql"}),
        "unity_dbsql": (db["host"] + "/ai-gateway/mcp-services/system.ai.dbsql", {"ai-gateway"}),
    }.get(db["endpoint_mode"], (None, set()))
    if db["mcp_url"] != endpoint or db["oauth_scope"] not in scopes:
        raise ValueError("MCP_ENDPOINT_OR_SCOPE_MISMATCH")
    if db["subject_claim"] not in {"email", "preferred_username", "upn"}:
        raise ValueError("HUMAN_MAPPING_CLAIM_REQUIRED")
    if not isinstance(db["public_client_exchange_enabled"], bool):
        raise ValueError("EXCHANGE_ENABLEMENT_MUST_BE_BOOLEAN")
    if set(db["tables"]) != set(AGENTS) or len(set(db["tables"].values())) != 2:
        raise ValueError("TWO_DISTINCT_CANARY_TABLES_REQUIRED")
    for table in db["tables"].values():
        canary_query(table)
    return config


def load_config(path):
    return validate_config(json.loads(Path(path).read_text()))


def aws_sessions(config):
    validate_config(config)
    sessions = {}
    for name, account in config["accounts"].items():
        session = boto3.Session(profile_name=account["profile"], region_name=config["region"])
        if session.client("sts").get_caller_identity()["Account"] != account["id"]:
            raise ValueError("PROFILE_ACCOUNT_MISMATCH:" + name)
        sessions[name] = session
    return sessions


def outputs(config, sessions, account, name):
    return stack_outputs(sessions[account], config["project"] + "-" + name)


def callers(config):
    return {
        "origin": config["login_client_id"],
        "data": config["accounts"]["platform"]["gateway_client_id"],
        **{agent: config["agents"][agent]["client_id"] for agent in AGENTS},
    }


def prepare_phase(root, config, sessions, phase):
    validate_config(config)
    if phase not in PHASES:
        raise ValueError("UNKNOWN_PHASE")
    if phase == "data-bindings" and not config["databricks"]["public_client_exchange_enabled"]:
        raise ValueError("CONFIRM_PUBLIC_CLIENT_TOKEN_EXCHANGE_ENABLEMENT_FIRST")
    plans = []

    def add(name, account, params):
        path = Path(root) / "config" / f"local.journey-{name}-{account}.json"
        path.write_text(json.dumps(params, indent=2) + "\n")
        args = [
            "uv",
            "run",
            "--extra",
            "banking",
            "python",
            "scripts/banking_deploy.py",
            name,
            "--scenario",
            "journey",
            "--profile",
            config["accounts"][account]["profile"],
            "--account",
            config["accounts"][account]["id"],
            "--region",
            config["region"],
            "--stack",
            config["project"] + "-" + name,
            "--parameters",
            str(path),
        ]
        plans.append(
            {"account": account, "template": name, "args": args, "command": shlex.join(args)}
        )

    def gateway(account):
        return outputs(config, sessions, account, account + "-gateway")

    def bucket(account):
        return outputs(config, sessions, account, "bootstrap")["ArtifactBucket"]

    if phase == "bootstrap":
        for account in ACCOUNTS:
            add("bootstrap", account, {})
    elif phase == "gateways":
        for account in ACCOUNTS:
            values = config["accounts"][account]
            params = {
                "Project": config["project"] + "-" + account,
                "TenantId": config["tenant_id"],
                "GatewayClientId": values["gateway_client_id"],
                "EngineName": config["project"].replace("-", "_") + "_" + account,
            }
            if account != "platform":
                params["CallerClientId"] = callers(config)[account]
            if account == "data":
                db = config["databricks"]
                params.update(
                    DatabricksHost=db["host"],
                    DatabricksClientId=db["client_id"],
                    DatabricksSecretArn=db["secret_arn"],
                )
            else:
                params["GatewaySecretArn"] = values["gateway_secret_arn"]
            add(account + "-gateway", account, params)
    elif phase.endswith("-bindings"):
        account = phase.removesuffix("-bindings")
        gw = gateway(account)
        params = {
            key: gw[key]
            for key in ("GatewayId", "GatewayArn", "PolicyEngineId", "OAuthProviderArn")
        }
        params.update(
            TenantId=config["tenant_id"], AllowedUserOids=",".join(config["users"].values())
        )
        if account != "platform":
            params["CallerClientId"] = callers(config)[account]
        if account != "origin":
            params.update(
                {agent.title() + "Table": config["databricks"]["tables"][agent] for agent in AGENTS}
            )
        if account == "data":
            params.update(
                DatabricksMcpUrl=config["databricks"]["mcp_url"],
                DatabricksScope=config["databricks"]["oauth_scope"],
            )
        else:
            params.update(
                {
                    agent.title() + "ClientId": config["agents"][agent]["client_id"]
                    for agent in AGENTS
                }
            )
            if account == "platform":
                params.update(
                    DataEndpoint=gateway("data")["GatewayUrl"],
                    DataClientId=config["accounts"]["data"]["gateway_client_id"],
                )
            else:
                for agent in AGENTS:
                    arn = outputs(config, sessions, "origin", agent + "-agent")["RuntimeArn"]
                    params[agent.title() + "Endpoint"] = runtime_url(config["region"], arn)
        add(phase, account, params)
    elif phase in {"registry", "approve-registry"}:
        add(
            "registry",
            "platform",
            {
                "ArtifactBucket": bucket("platform"),
                "Project": config["project"],
                "OriginAccount": config["accounts"]["origin"]["id"],
                "GatewayUrl": gateway("platform")["GatewayUrl"],
                "ApproveRecords": "true" if phase == "approve-registry" else "false",
            },
        )
    elif phase == "agents":
        catalog = outputs(config, sessions, "platform", "registry")
        for agent in AGENTS:
            params = {
                "Project": config["project"],
                "ArtifactBucket": bucket("origin"),
                "TenantId": config["tenant_id"],
                "RuntimeClientId": config["agents"][agent]["client_id"],
                "CallerClientId": config["accounts"]["origin"]["gateway_client_id"],
                "AgentSecretArn": config["agents"][agent]["secret_arn"],
                "GatewayArn": gateway("origin")["GatewayArn"],
                "HubUrl": gateway("platform")["GatewayUrl"],
                "HubClientId": config["accounts"]["platform"]["gateway_client_id"],
                "RegistryArn": catalog["RegistryArn"],
                "RegistryConsumerRoleArn": catalog["RegistryConsumerRoleArn"],
                "SubjectClaim": config["databricks"]["subject_claim"],
                "RuntimeName": config["project"].replace("-", "_") + "_" + agent,
                **{name.title() + "Table": config["databricks"]["tables"][name] for name in AGENTS},
            }
            add(agent + "-agent", "origin", params)
    return plans


def check_auth(auth, config, audience, caller=None):
    expected = {
        "tid": config["tenant_id"],
        "ver": "2.0",
        "scp": SCOPE,
        **({"azp": caller} if caller else {}),
    }
    if (
        auth.get("discoveryUrl")
        != f"https://login.microsoftonline.com/{config['tenant_id']}/v2.0/.well-known/openid-configuration"
        or auth.get("allowedAudience") != [audience]
    ):
        raise ValueError("AUTHORIZER_ISSUER_AUDIENCE_MISMATCH")
    claims = {c["inboundTokenClaimName"]: c for c in auth.get("customClaims", [])}
    if set(claims) != set(expected):
        raise ValueError("AUTHORIZER_CLAIMS_MISMATCH")
    for key, value in expected.items():
        match = claims[key]["authorizingClaimMatchValue"]
        if match != {
            "claimMatchOperator": "EQUALS",
            "claimMatchValue": {"matchValueString": value},
        }:
            raise ValueError("AUTHORIZER_CLAIM_VALUE_MISMATCH")


def preflight(config, sessions):
    """Leitura das fronteiras e das regras implantadas; não marca integração como aprovada."""
    validate_config(config)
    if not config["databricks"]["public_client_exchange_enabled"]:
        raise ValueError("PUBLIC_CLIENT_EXCHANGE_ENABLEMENT_NOT_CONFIRMED")
    gateways = {name: outputs(config, sessions, name, name + "-gateway") for name in ACCOUNTS}
    agents = {name: outputs(config, sessions, "origin", name + "-agent") for name in AGENTS}
    for account, stack in gateways.items():
        control = sessions[account].client("bedrock-agentcore-control")
        actual = control.get_gateway(gatewayIdentifier=stack["GatewayId"])
        if (
            actual["status"] != "READY"
            or actual["gatewayArn"] != stack["GatewayArn"]
            or actual["gatewayArn"].split(":")[4] != config["accounts"][account]["id"]
            or actual["gatewayUrl"] != stack["GatewayUrl"]
            or actual["authorizerType"] != "CUSTOM_JWT"
            or actual["policyEngineConfiguration"]
            != {"arn": stack["PolicyEngineArn"], "mode": "ENFORCE"}
        ):
            raise ValueError("GATEWAY_MISMATCH:" + account)
        checked_gateway(actual["gatewayUrl"], config["region"])
        check_auth(
            actual["authorizerConfiguration"]["customJWTAuthorizer"],
            config,
            config["accounts"][account]["gateway_client_id"],
            callers(config).get(account),
        )
        provider = control.get_oauth2_credential_provider(
            name=config["project"] + "-" + account + "-obo"
        )
        oauth_config = provider["oauth2ProviderConfigOutput"]["customOauth2ProviderConfig"]
        expected_grant = "TOKEN_EXCHANGE" if account == "data" else "JWT_AUTHORIZATION_GRANT"
        expected_client = (
            config["databricks"]["client_id"]
            if account == "data"
            else config["accounts"][account]["gateway_client_id"]
        )
        if (
            provider["credentialProviderArn"] != stack["OAuthProviderArn"]
            or provider["credentialProviderArn"].split(":")[4] != config["accounts"][account]["id"]
            or oauth_config.get("clientId") != expected_client
            or oauth_config.get("onBehalfOfTokenExchangeConfig", {}).get("grantType")
            != expected_grant
        ):
            raise ValueError("IDENTITY_PROVIDER_MISMATCH:" + account)
        expected = cedar(
            account,
            stack["GatewayArn"],
            config["tenant_id"],
            callers(config),
            list(config["users"].values()),
            config["databricks"]["tables"],
        )
        policies = list(
            pages(control, "list_policies", "policies", policyEngineId=stack["PolicyEngineId"])
        )
        if {p["name"] for p in policies} != set(expected):
            raise ValueError("POLICY_SET_MISMATCH:" + account)
        for policy in policies:
            if (
                policy.get("status") != "ACTIVE"
                or policy.get("enforcementMode") != "ACTIVE"
                or policy.get("definition", {}).get("cedar", {}).get("statement", "").strip()
                != expected[policy["name"]].strip()
            ):
                raise ValueError("POLICY_DEFINITION_MISMATCH:" + account)
        targets = list(
            pages(control, "list_gateway_targets", "items", gatewayIdentifier=stack["GatewayId"])
        )
        if {t["name"] for t in targets} != ({"dados"} if account == "platform" else set(AGENTS)):
            raise ValueError("TARGET_SET_MISMATCH:" + account)
        for item in targets:
            detail = control.get_gateway_target(
                gatewayIdentifier=stack["GatewayId"], targetId=item["targetId"]
            )
            endpoint = (
                gateways["data"]["GatewayUrl"]
                if account == "platform"
                else config["databricks"]["mcp_url"]
                if account == "data"
                else runtime_url(config["region"], agents[item["name"]]["RuntimeArn"])
            )
            credentials = detail["credentialProviderConfigurations"]
            oauth = credentials[0].get("credentialProvider", {}).get("oauthCredentialProvider", {})
            scope = (
                config["databricks"]["oauth_scope"]
                if account == "data"
                else "api://"
                + (
                    config["accounts"]["data"]["gateway_client_id"]
                    if account == "platform"
                    else config["agents"][item["name"]]["client_id"]
                )
                + "/.default"
            )
            if (
                detail["status"] != "READY"
                or detail["targetConfiguration"]["mcp"]["mcpServer"]["endpoint"] != endpoint
                or len(credentials) != 1
                or credentials[0]["credentialProviderType"] != "OAUTH"
                or oauth.get("grantType") != "TOKEN_EXCHANGE"
                or oauth.get("providerArn") != stack["OAuthProviderArn"]
                or oauth.get("scopes") != [scope]
            ):
                raise ValueError("TARGET_OBO_MISMATCH:" + account)
    control = sessions["origin"].client("bedrock-agentcore-control")
    for agent in AGENTS:
        runtime = control.get_agent_runtime(agentRuntimeId=agents[agent]["RuntimeId"])
        auth = runtime["authorizerConfiguration"]["customJWTAuthorizer"]
        check_auth(
            auth,
            config,
            config["agents"][agent]["client_id"],
            config["accounts"]["origin"]["gateway_client_id"],
        )
        if (
            runtime["status"] != "READY"
            or runtime["agentRuntimeArn"].split(":")[4] != config["accounts"]["origin"]["id"]
            or auth.get("allowedWorkloadConfiguration")
            != {"hostingEnvironments": [{"arn": gateways["origin"]["GatewayArn"]}]}
        ):
            raise ValueError("ORIGIN_RUNTIME_BOUNDARY_MISMATCH")
        provider = control.get_oauth2_credential_provider(
            name=config["project"] + "-" + agent + "-obo"
        )
        oauth_config = provider["oauth2ProviderConfigOutput"]["customOauth2ProviderConfig"]
        if (
            oauth_config.get("clientId") != config["agents"][agent]["client_id"]
            or oauth_config.get("onBehalfOfTokenExchangeConfig", {}).get("grantType")
            != "JWT_AUTHORIZATION_GRANT"
        ):
            raise ValueError("AGENT_IDENTITY_PROVIDER_MISMATCH")
    catalog = outputs(config, sessions, "platform", "registry")
    registry = (
        sessions["platform"]
        .client("bedrock-agentcore-control")
        .get_registry(registryId=catalog["RegistryId"])
    )
    if (
        registry["registryArn"] != catalog["RegistryArn"]
        or registry["status"] != "READY"
        or registry["authorizerType"] != "AWS_IAM"
        or registry["approvalConfiguration"]["autoApproval"] is not False
    ):
        raise ValueError("REGISTRY_GOVERNANCE_MISMATCH")
    return {
        "mode": "AWS_READ_ONLY",
        "invocation_verified": False,
        "gateways": gateways,
        "agents": agents,
    }


def verify_login(token, config, user):
    identity = verify_entra(
        token,
        tenant=config["tenant_id"],
        audience=config["accounts"]["origin"]["gateway_client_id"],
        version="2.0",
    )
    if (
        identity.claims.get("oid") != config["users"][user]
        or identity.claims.get("azp") != config["login_client_id"]
        or identity.claims.get("scp") != SCOPE
        or identity.claims.get("ver") != "2.0"
    ):
        raise ValueError("LOGIN_USER_OR_APPLICATION_MISMATCH")
    return identity


def login(config, user):
    """Nova sessão MSAL por usuário, sem cache em disco ou token em output."""
    import msal

    app = msal.PublicClientApplication(
        config["login_client_id"],
        authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
    )
    flow = app.initiate_device_flow(
        scopes=[f"api://{config['accounts']['origin']['gateway_client_id']}/{SCOPE}"]
    )
    if "user_code" not in flow:
        raise RuntimeError("DEVICE_FLOW_NOT_AVAILABLE_USE_APPROVED_PKCE_CLIENT")
    print(flow["message"])
    response = app.acquire_token_by_device_flow(flow)
    if "access_token" not in response:
        raise RuntimeError("LOGIN_FAILED")
    verify_login(response["access_token"], config, user)
    return response["access_token"]


async def run_case(config, environment, token, *, user, agent, capability, case):
    identity = verify_login(token, config, user)
    if agent not in AGENTS or capability not in AGENTS:
        raise ValueError("UNKNOWN_AGENT_OR_CAPABILITY")
    url = environment["gateways"]["origin"]["GatewayUrl"]
    request_id = str(uuid4())
    async with gateway_session(url, token, {url}, timeout_seconds=600) as session:
        result = tool_json(
            await session.call_tool(
                agent + "___consultar",
                {"capacidade": capability, "request_id": request_id},
            )
        )
    result = result.get("result", result)
    if (
        result.get("request_id") != request_id
        or result.get("user_ref") != identity.summary()["user_ref"]
        or result.get("agent") != agent
        or result.get("mode") != "AWS_LIVE"
    ):
        raise ValueError("RUNTIME_EVIDENCE_MISMATCH")
    return {**result, "case": case}
