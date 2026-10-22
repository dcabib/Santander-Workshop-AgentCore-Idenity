"""Preparação IaC, verificações e invocações reais do notebook 11."""

import json
import re
import shlex
from pathlib import Path
from uuid import UUID

import boto3
import httpx

from santander_demo.banking.agent import checked_gateway
from santander_demo.banking.client import call_tool, runtime_url, stack_outputs
from santander_demo.banking.spec import LOBS
from santander_demo.cloud import gateway_session
from santander_demo.federation.spec import ACCOUNTS, PREFIXES, SCOPE, cedar, central_name
from santander_demo.identity import verify_entra


def validate_config(config):
    if set(config["accounts"]) != set(ACCOUNTS):
        raise ValueError("FOUR_NAMED_ACCOUNTS_REQUIRED")
    ids = [item["id"] for item in config["accounts"].values()]
    if len(set(ids)) != 4 or any(not re.fullmatch(r"\d{12}", value) for value in ids):
        raise ValueError("FOUR_DISTINCT_ACCOUNTS_REQUIRED")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,20}", config["project"]):
        raise ValueError("INVALID_PROJECT_NAME")
    if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d", config["region"]):
        raise ValueError("INVALID_REGION")
    text = json.dumps(config)
    if "REPLACE" in text or any(key in text for key in ['"client_secret"', '"access_token"']):
        raise ValueError("IDENTIFIERS_ONLY_COMPLETE_CONFIG")
    UUID(config["tenant_id"])
    UUID(config["expected_user_oid"])
    UUID(config["login_client_id"])
    applications = [config["login_client_id"]]
    for name, account in config["accounts"].items():
        UUID(account["gateway_client_id"])
        applications.append(account["gateway_client_id"])
        if name != "platform":
            UUID(account["runtime_client_id"])
            applications.append(account["runtime_client_id"])
        if not account["profile"] or not account["allowed_user_oids"]:
            raise ValueError("PROFILE_AND_USER_ALLOWLIST_REQUIRED")
        for user in account["allowed_user_oids"]:
            UUID(user)
        if config["expected_user_oid"] not in account["allowed_user_oids"]:
            raise ValueError("BASELINE_USER_MUST_HAVE_READ_ACCESS_IN_ALL_ACCOUNTS")
        prefix = f"arn:aws:secretsmanager:{config['region']}:{account['id']}:secret:"
        if not account["gateway_secret_arn"].startswith(prefix):
            raise ValueError("IDENTITY_SECRET_MUST_BELONG_TO_LOCAL_ACCOUNT_AND_REGION")
    if len(set(applications)) != 8:
        raise ValueError("EIGHT_DISTINCT_ENTRA_APPLICATIONS_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9]{10}", config["knowledge_base_id"]):
        raise ValueError("LENDING_KNOWLEDGE_BASE_REQUIRED")
    if not config.get("model_id"):
        raise ValueError("BEDROCK_MODEL_ID_REQUIRED")
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


def stack_name(config, template):
    return config["project"] + "-" + template


def caller(config, account):
    return (
        config["login_client_id"]
        if account == "platform"
        else config["accounts"]["platform"]["gateway_client_id"]
    )


def outputs(config, sessions, account, suffix):
    return stack_outputs(sessions[account], stack_name(config, account + "-" + suffix))


def prepare_phase(root, config, sessions, phase):
    """Só prepara parâmetros/comandos. Mutações pertencem ao wrapper CloudFormation."""
    validate_config(config)
    plans = []

    def add(name, account, params):
        path = Path(root) / "config" / f"local.federation-{name}-{account}.json"
        path.parent.mkdir(exist_ok=True)
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
            "federation",
            "--profile",
            config["accounts"][account]["profile"],
            "--account",
            config["accounts"][account]["id"],
            "--region",
            config["region"],
            "--stack",
            stack_name(config, name),
            "--parameters",
            str(path),
        ]
        plans.append(
            {"account": account, "template": name, "args": args, "command": shlex.join(args)}
        )

    def bucket(account):
        return stack_outputs(sessions[account], stack_name(config, "bootstrap"))["ArtifactBucket"]

    if phase == "bootstrap":
        for account in ACCOUNTS:
            add("bootstrap", account, {})
    elif phase == "gateways":
        for account, values in config["accounts"].items():
            add(
                account + "-gateway",
                account,
                {
                    "Project": config["project"],
                    "TenantId": config["tenant_id"],
                    "GatewayClientId": values["gateway_client_id"],
                    "CallerClientId": caller(config, account),
                    "GatewaySecretArn": values["gateway_secret_arn"],
                    "EngineName": config["project"].replace("-", "_") + "_policy",
                },
            )
    elif phase == "backends":
        kb = (
            sessions["lending-wealth"]
            .client("bedrock-agent")
            .get_knowledge_base(knowledgeBaseId=config["knowledge_base_id"])["knowledgeBase"]
        )
        if kb["status"] != "ACTIVE":
            raise ValueError("LENDING_KB_NOT_ACTIVE")
        for lob in LOBS:
            gateway = outputs(config, sessions, lob, "gateway")
            values = config["accounts"][lob]
            params = {
                "Project": config["project"],
                "ArtifactBucket": bucket(lob),
                "GatewayArn": gateway["GatewayArn"],
                "TenantId": config["tenant_id"],
                "RuntimeClientId": values["runtime_client_id"],
                "CallerClientId": values["gateway_client_id"],
                "RuntimeName": config["project"].replace("-", "_") + "_" + PREFIXES[lob],
            }
            if lob == "lending-wealth":
                params["KnowledgeBaseId"] = config["knowledge_base_id"]
            add(lob + "-backend", lob, params)
    elif phase in {"domain-bindings", "platform-bindings"}:
        for account in LOBS if phase == "domain-bindings" else ["platform"]:
            gateway = outputs(config, sessions, account, "gateway")
            params = {
                key: gateway[key]
                for key in ["GatewayId", "GatewayArn", "PolicyEngineId", "OAuthProviderArn"]
            }
            params.update(
                TenantId=config["tenant_id"],
                CallerClientId=caller(config, account),
                AllowedUserOids=",".join(config["accounts"][account]["allowed_user_oids"]),
            )
            for lob in LOBS if account == "platform" else [account]:
                if account == "platform":
                    endpoint = outputs(config, sessions, lob, "gateway")["GatewayUrl"]
                    audience = config["accounts"][lob]["gateway_client_id"]
                    checked_gateway(endpoint, config["region"])
                else:
                    arn = outputs(config, sessions, lob, "backend")["RuntimeArn"]
                    if arn.split(":")[4] != config["accounts"][lob]["id"]:
                        raise ValueError("BACKEND_ACCOUNT_MISMATCH")
                    endpoint = runtime_url(config["region"], arn)
                    audience = config["accounts"][lob]["runtime_client_id"]
                prefix = PREFIXES[lob].title()
                params[prefix + "Endpoint"] = endpoint
                params[prefix + "Scope"] = f"api://{audience}/.default"
            add(account + "-bindings", account, params)
    elif phase == "registry":
        add(
            "registry",
            "platform",
            {
                "Project": config["project"],
                "ArtifactBucket": bucket("platform"),
                "GatewayUrl": outputs(config, sessions, "platform", "gateway")["GatewayUrl"],
            },
        )
    else:
        raise ValueError("UNKNOWN_DEPLOY_PHASE")
    return plans


def verify_token(token, config):
    identity = verify_entra(
        token,
        tenant=config["tenant_id"],
        audience=config["accounts"]["platform"]["gateway_client_id"],
        version="2.0",
    )
    if (
        identity.claims.get("oid") != config["expected_user_oid"]
        or identity.claims.get("azp") != config["login_client_id"]
        or identity.claims.get("scp") != SCOPE
        or identity.claims.get("ver") != "2.0"
    ):
        raise ValueError("PLATFORM_USER_APPLICATION_OR_SCOPE_MISMATCH")
    return identity.summary()


def login(config):
    """Device Code público, se permitido pelo tenant; token só na memória."""
    import msal

    app = msal.PublicClientApplication(
        config["login_client_id"],
        authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
    )
    flow = app.initiate_device_flow(
        scopes=[f"api://{config['accounts']['platform']['gateway_client_id']}/{SCOPE}"]
    )
    if "user_code" not in flow:
        raise RuntimeError("ENTRA_DEVICE_FLOW_UNAVAILABLE")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError("ENTRA_LOGIN_FAILED")
    token = result["access_token"]
    verify_token(token, config)
    return token


def pages(client, operation, field, **kwargs):
    cursor, seen = None, set()
    while True:
        response = getattr(client, operation)(**kwargs, **({"nextToken": cursor} if cursor else {}))
        yield from response.get(field, [])
        cursor = response.get("nextToken")
        if not cursor:
            return
        if cursor in seen:
            raise RuntimeError("CONTROL_PAGINATION_LOOP")
        seen.add(cursor)


def check_authorizer(auth, config, audience, expected_caller):
    discovery = f"https://login.microsoftonline.com/{config['tenant_id']}/v2.0/.well-known/openid-configuration"
    claims = {v["inboundTokenClaimName"]: v for v in auth.get("customClaims", [])}
    if auth.get("discoveryUrl") != discovery or auth.get("allowedAudience") != [audience]:
        raise RuntimeError("JWT_ISSUER_OR_AUDIENCE_MISMATCH")
    for key, value in {
        "tid": config["tenant_id"],
        "azp": expected_caller,
        "ver": "2.0",
        "scp": SCOPE,
    }.items():
        wanted = {
            "inboundTokenClaimName": key,
            "inboundTokenClaimValueType": "STRING",
            "authorizingClaimMatchValue": {
                "claimMatchOperator": "EQUALS",
                "claimMatchValue": {"matchValueString": value},
            },
        }
        if claims.get(key) != wanted:
            raise RuntimeError("JWT_CLAIM_CONSTRAINT_MISMATCH:" + key)


def preflight(config, sessions):
    """Confere quatro fronteiras, incluindo Cedar implantado e Identity local."""
    validate_config(config)
    gateways = {a: outputs(config, sessions, a, "gateway") for a in ACCOUNTS}
    backends = {a: outputs(config, sessions, a, "backend") for a in LOBS}
    for account in ACCOUNTS:
        values, stack = config["accounts"][account], gateways[account]
        control = sessions[account].client("bedrock-agentcore-control")
        gw = control.get_gateway(gatewayIdentifier=stack["GatewayId"])
        if (
            gw["status"] != "READY"
            or gw["gatewayArn"] != stack["GatewayArn"]
            or gw["gatewayArn"].split(":")[4] != values["id"]
            or gw["gatewayUrl"] != stack["GatewayUrl"]
            or gw["authorizerType"] != "CUSTOM_JWT"
            or gw.get("policyEngineConfiguration")
            != {"arn": stack["PolicyEngineArn"], "mode": "ENFORCE"}
        ):
            raise RuntimeError("GATEWAY_BOUNDARY_MISMATCH:" + account)
        checked_gateway(gw["gatewayUrl"], config["region"])
        check_authorizer(
            gw["authorizerConfiguration"]["customJWTAuthorizer"],
            config,
            values["gateway_client_id"],
            caller(config, account),
        )
        provider = control.get_oauth2_credential_provider(name=config["project"] + "-obo")
        oauth = provider["oauth2ProviderConfigOutput"]["customOauth2ProviderConfig"]
        if (
            provider["credentialProviderArn"] != stack["OAuthProviderArn"]
            or provider["credentialProviderArn"].split(":")[4] != values["id"]
            or oauth["clientId"] != values["gateway_client_id"]
            or oauth.get("onBehalfOfTokenExchangeConfig", {}).get("grantType")
            != "JWT_AUTHORIZATION_GRANT"
            or provider["clientSecretArn"] != values["gateway_secret_arn"]
        ):
            raise RuntimeError("LOCAL_IDENTITY_OBO_MISMATCH:" + account)
        expected_rules = cedar(
            account,
            gw["gatewayArn"],
            config["tenant_id"],
            caller(config, account),
            values["allowed_user_oids"],
        )
        policies = list(
            pages(control, "list_policies", "policies", policyEngineId=stack["PolicyEngineId"])
        )
        if {p["name"] for p in policies} != set(expected_rules):
            raise RuntimeError("INDEPENDENT_POLICY_SET_MISMATCH:" + account)
        for policy in policies:
            actual = policy.get("definition", {}).get("cedar", {}).get("statement", "")
            # Whitespace is ignored outside values; configured identifiers contain no spaces.
            if (
                policy["status"] != "ACTIVE"
                or policy["enforcementMode"] != "ACTIVE"
                or re.sub(r"\s+", "", actual) != re.sub(r"\s+", "", expected_rules[policy["name"]])
            ):
                raise RuntimeError("CEDAR_DEFINITION_MISMATCH:" + account)
        targets = list(
            pages(control, "list_gateway_targets", "items", gatewayIdentifier=stack["GatewayId"])
        )
        expected_targets = set(PREFIXES.values()) if account == "platform" else {"backend"}
        if {t["name"] for t in targets} != expected_targets:
            raise RuntimeError("GATEWAY_TARGET_SET_MISMATCH:" + account)
        for target in targets:
            lob = (
                next(name for name in LOBS if PREFIXES[name] == target["name"])
                if account == "platform"
                else account
            )
            detail = control.get_gateway_target(
                gatewayIdentifier=stack["GatewayId"], targetId=target["targetId"]
            )
            audience = config["accounts"][lob][
                "gateway_client_id" if account == "platform" else "runtime_client_id"
            ]
            endpoint = (
                gateways[lob]["GatewayUrl"]
                if account == "platform"
                else runtime_url(config["region"], backends[lob]["RuntimeArn"])
            )
            credentials = detail["credentialProviderConfigurations"]
            expected_credentials = [
                {
                    "credentialProviderType": "OAUTH",
                    "credentialProvider": {
                        "oauthCredentialProvider": {
                            "providerArn": stack["OAuthProviderArn"],
                            "grantType": "TOKEN_EXCHANGE",
                            "scopes": [f"api://{audience}/.default"],
                            "customParameters": {"requested_token_use": "on_behalf_of"},
                        }
                    },
                }
            ]
            if (
                detail["status"] != "READY"
                or detail["targetConfiguration"]["mcp"]["mcpServer"]["endpoint"] != endpoint
                or credentials != expected_credentials
            ):
                raise RuntimeError("OBO_TARGET_BOUNDARY_MISMATCH:" + account)
        if account != "platform":
            runtime = control.get_agent_runtime(agentRuntimeId=backends[account]["RuntimeId"])
            auth = runtime["authorizerConfiguration"]["customJWTAuthorizer"]
            check_authorizer(auth, config, values["runtime_client_id"], values["gateway_client_id"])
            if (
                runtime["status"] != "READY"
                or runtime["agentRuntimeArn"].split(":")[4] != values["id"]
                or auth.get("allowedWorkloadConfiguration")
                != {"hostingEnvironments": [{"arn": stack["GatewayArn"]}]}
                or "authorization"
                not in {
                    h.lower()
                    for h in runtime.get("requestHeaderConfiguration", {}).get(
                        "requestHeaderAllowlist", []
                    )
                }
            ):
                raise RuntimeError("BACKEND_MUST_REQUIRE_LOCAL_GATEWAY:" + account)
    registry = stack_outputs(sessions["platform"], stack_name(config, "registry"))
    control = sessions["platform"].client("bedrock-agentcore-control")
    catalog = control.get_registry(registryId=registry["RegistryId"])
    if (
        catalog["status"] != "READY"
        or catalog["authorizerType"] != "AWS_IAM"
        or catalog["approvalConfiguration"]["autoApproval"]
    ):
        raise RuntimeError("REGISTRY_NOT_GOVERNED")
    platform = gateways["platform"]
    return {
        "mode": "AWS_READ_ONLY",
        "invocation_verified": False,
        "region": config["region"],
        "gateway_url": platform["GatewayUrl"],
        "gateways": gateways,
        "backends": backends,
        "registry_arn": registry["RegistryArn"],
        "guardrail_id": platform["GuardrailId"],
        "guardrail_version": platform["GuardrailVersion"],
        "model_id": config["model_id"],
    }


async def verify_chain(environment, token, config):
    expected = verify_token(token, config)
    results = {}
    for lob in LOBS:
        identity = await call_tool(environment, token, central_name(lob, "whoami"), {})
        if (
            identity.get("mode") != "AWS_VERIFIED_JWT"
            or identity.get("lob") != lob
            or identity.get("user_ref") != expected["user_ref"]
            or identity.get("caller") != config["accounts"][lob]["gateway_client_id"]
            or identity.get("audience") != config["accounts"][lob]["runtime_client_id"]
            or identity.get("delegated") is not True
        ):
            raise RuntimeError("END_TO_END_USER_OR_ACTOR_MISMATCH:" + lob)
        results[lob] = {
            "user_preserved": True,
            "local_gateway_actor": True,
            "runtime_audience": True,
        }
    return {"mode": "AWS_LIVE", "obo": results}


async def probe_policy(environment, token, customer):
    """Erro genérico nunca é rotulado como prova de Policy ou de um salto específico."""
    from mcp.shared.exceptions import McpError

    if customer not in {"C007", "C008"}:
        raise ValueError("USE_DEDICATED_READ_ONLY_NEGATIVE_CASE")
    async with gateway_session(
        environment["gateway_url"], token, {environment["gateway_url"]}
    ) as session:
        try:
            result = await session.call_tool(
                central_name("retail-banking", "get_profile"), {"customer_id": customer}
            )
            message = " ".join(c.text for c in result.content if c.type == "text")
            if not result.isError:
                return {"outcome": "NOT_PROVEN", "customer": customer}
        except McpError as exc:
            message = exc.error.message
    return {
        "customer": customer,
        "outcome": "POLICY_DENIAL_REPORTED"
        if "tool call not allowed" in message.lower()
        else "UNCLASSIFIED_ERROR",
        "expected_boundary": "platform" if customer == "C007" else "retail-banking",
        "boundary_and_backend_non_invocation": "REVIEW_ACCOUNT_LOGS",
    }


async def probe_wrong_audience(environment, token):
    """Token da plataforma no Gateway Retail: deve ser rejeitado por autenticação."""
    url = environment["gateways"]["retail-banking"]["GatewayUrl"]
    checked_gateway(url, environment["region"])
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "negative-auth-probe", "version": "1.0"},
                },
            },
        )
    if response.status_code not in {401, 403}:
        raise RuntimeError("WRONG_AUDIENCE_NOT_REJECTED_BY_AUTH")
    return {
        "mode": "AWS_LIVE",
        "http_status": response.status_code,
        "auth_rejection_observed": True,
    }
