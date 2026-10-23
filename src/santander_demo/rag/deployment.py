"""Preparação de parâmetros e preflight somente leitura; mutações ficam no wrapper IaC."""

import copy
import json
import shlex
from pathlib import Path

from santander_demo.banking.agent import checked_gateway
from santander_demo.federation.client import pages
from santander_demo.rag import cognito
from santander_demo.rag.client import validate_config
from santander_demo.rag.contract import SCOPE, cedar, connector_configuration
from santander_demo.rag.corpus import corpus_digest

PHASES = ("bootstrap", "identity", "data", "access")


def outputs(session, config, phase):
    stack = session.client("cloudformation").describe_stacks(
        StackName=f"{config['project']}-rag-{phase}"
    )["Stacks"][0]
    return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}


def prepare_phase(root, config, session, phase):
    validate_config(config)
    if phase not in PHASES:
        raise ValueError("UNKNOWN_PHASE")
    if session.client("sts").get_caller_identity()["Account"] != config["account_id"]:
        raise ValueError("WRONG_ACCOUNT")
    params = {}
    if phase not in {"bootstrap", "identity"}:
        params = {
            "Project": config["project"],
            **{f"User{label.upper()}Oid": u["oid"] for label, u in config["users"].items()},
            **{f"User{label.upper()}Email": u["email"] for label, u in config["users"].items()},
        }
    if phase == "identity":
        params = {
            "Project": config["project"],
            "ArtifactBucket": outputs(session, config, "bootstrap")["ArtifactBucket"],
        }
    elif phase == "data":
        params.update(
            ArtifactBucket=outputs(session, config, "bootstrap")["ArtifactBucket"],
            CorpusDigest=corpus_digest(config["users"]),
        )
    elif phase == "access":
        del params["UserDEmail"]
        del params["UserDOid"]
        source = outputs(session, config, "data")
        params.update(
            EngineName=config["project"].replace("-", "_") + "_rag",
            KnowledgeBaseId=source["KnowledgeBaseId"],
            KnowledgeBaseArn=source["KnowledgeBaseArn"],
            CallerPrincipalArn=config["caller_principal_arn"],
            ModelArn=config["model_arn"],
        )
        if config.get("auth_provider") == "cognito":
            params.update(
                UserPoolId=config["user_pool_id"], LoginClientId=config["login_client_id"]
            )
        else:
            params.update(
                TenantId=config["tenant_id"],
                BrokerClientId=config["broker_client_id"],
                GatewayClientId=config["gateway_client_id"],
                BrokerSecretArn=config["broker_secret_arn"],
            )
    path = Path(root) / "config" / f"local.rag-{phase}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params, indent=2) + "\n")
    path.chmod(0o600)
    args = [
        "uv",
        "run",
        "--extra",
        "banking",
        "python",
        "scripts/banking_deploy.py",
        "access-cognito"
        if phase == "access" and config.get("auth_provider") == "cognito"
        else phase,
        "--scenario",
        "rag",
        "--profile",
        config["profile"],
        "--account",
        config["account_id"],
        "--region",
        config["region"],
        "--stack",
        f"{config['project']}-rag-{phase}",
        "--parameters",
        str(path),
    ]
    return {"phase": phase, "args": args, "command": shlex.join(args)}


def preflight(config, session):
    validate_config(config)
    if session.client("sts").get_caller_identity()["Account"] != config["account_id"]:
        raise ValueError("WRONG_ACCOUNT")
    data = outputs(session, config, "data")
    access = outputs(session, config, "access")
    kb = session.client("bedrock-agent")
    actual = kb.get_knowledge_base(knowledgeBaseId=data["KnowledgeBaseId"])["knowledgeBase"]
    if (
        actual["status"] != "ACTIVE"
        or actual["knowledgeBaseConfiguration"]["type"] != "MANAGED"
        or actual["knowledgeBaseArn"] != data["KnowledgeBaseArn"]
    ):
        raise ValueError("MANAGED_KB_NOT_READY")
    sources = list(
        pages(
            kb, "list_data_sources", "dataSourceSummaries", knowledgeBaseId=data["KnowledgeBaseId"]
        )
    )
    if {s["dataSourceId"] for s in sources} != {data["DataSourceId"]}:
        raise ValueError("UNEXPECTED_DATA_SOURCE_MAY_BYPASS_ACL")
    source = kb.get_data_source(
        knowledgeBaseId=data["KnowledgeBaseId"], dataSourceId=data["DataSourceId"]
    )["dataSource"]
    ds = source["dataSourceConfiguration"]
    cp = ds.get("managedKnowledgeBaseConnectorConfiguration", {}).get("connectorParameters", {})
    # GetDataSource devolve este campo Document como uma string JSON.
    if isinstance(cp, str):
        cp = json.loads(cp)
    if (
        source["status"] != "AVAILABLE"
        or ds["type"] != "MANAGED_KNOWLEDGE_BASE_CONNECTOR"
        or not isinstance(cp, dict)
        or cp.get("aclEnabled") is not True
        or cp.get("connectionConfiguration", {}).get("bucketName") != data["SourceBucket"]
        or cp.get("aclConfiguration", {}).get("globalAccessControlListS3Uri")
        != f"s3://{data['SourceBucket']}/acl/global-acl.json"
    ):
        raise ValueError("NATIVE_ACL_NOT_ENABLED")
    job = kb.get_ingestion_job(
        knowledgeBaseId=data["KnowledgeBaseId"],
        dataSourceId=data["DataSourceId"],
        ingestionJobId=data["IngestionJobId"],
    )["ingestionJob"]
    if job["status"] != "COMPLETE" or job.get("statistics", {}).get("numberOfDocumentsFailed", 0):
        raise ValueError("CORPUS_NOT_INGESTED")
    control = session.client("bedrock-agentcore-control")
    gw = control.get_gateway(gatewayIdentifier=access["GatewayId"])
    if (
        gw["status"] != "READY"
        or gw["gatewayArn"] != access["GatewayArn"]
        or gw["gatewayUrl"] != access["GatewayUrl"]
        or gw["authorizerType"] != "CUSTOM_JWT"
        or gw["policyEngineConfiguration"] != {"arn": access["PolicyEngineArn"], "mode": "ENFORCE"}
    ):
        raise ValueError("GATEWAY_NOT_ENFORCING")
    checked_gateway(gw["gatewayUrl"], config["region"])
    auth = gw["authorizerConfiguration"]["customJWTAuthorizer"]
    expected_claims = (
        {"token_use": "id"}
        if config.get("auth_provider") == "cognito"
        else {
            "tid": config["tenant_id"],
            "azp": config["broker_client_id"],
            "ver": "2.0",
            "scp": SCOPE,
        }
    )
    expected_rules = [
        {
            "inboundTokenClaimName": key,
            "inboundTokenClaimValueType": "STRING",
            "authorizingClaimMatchValue": {
                "claimMatchOperator": "EQUALS",
                "claimMatchValue": {"matchValueString": value},
            },
        }
        for key, value in expected_claims.items()
    ]
    discovery = (
        cognito.issuer(config) + "/.well-known/openid-configuration"
        if config.get("auth_provider") == "cognito"
        else f"https://login.microsoftonline.com/{config['tenant_id']}/v2.0/.well-known/openid-configuration"
    )
    audience = (
        config["login_client_id"]
        if config.get("auth_provider") == "cognito"
        else config["gateway_client_id"]
    )
    if (
        auth.get("discoveryUrl") != discovery
        or auth.get("allowedAudience") != [audience]
        or sorted(auth.get("customClaims", []), key=lambda c: c["inboundTokenClaimName"])
        != sorted(expected_rules, key=lambda c: c["inboundTokenClaimName"])
    ):
        raise ValueError("GATEWAY_IDENTITY_MISMATCH")
    targets = list(
        pages(control, "list_gateway_targets", "items", gatewayIdentifier=access["GatewayId"])
    )
    if {t["targetId"] for t in targets} != {access["TargetId"]}:
        raise ValueError("UNEXPECTED_GATEWAY_TARGET")
    target = control.get_gateway_target(
        gatewayIdentifier=access["GatewayId"], targetId=access["TargetId"]
    )
    actual_connector = copy.deepcopy(target["targetConfiguration"]["mcp"].get("connector", {}))
    # A API acrescenta a versão resolvida, mesmo quando o template omite Version.
    connector_version = actual_connector.get("source", {}).pop("version", None)
    if (
        target["status"] != "READY"
        or connector_version not in {None, "1.0.0"}
        or target["credentialProviderConfigurations"]
        != [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
        or actual_connector != connector_configuration(data["KnowledgeBaseId"])
    ):
        raise ValueError("CONNECTOR_CONTRACT_MISMATCH")
    expected = (
        cognito.policies(
            access["GatewayArn"], cognito.issuer(config), config["login_client_id"], config["users"]
        )
        if config.get("auth_provider") == "cognito"
        else cedar(
            access["GatewayArn"], config["tenant_id"], config["broker_client_id"], config["users"]
        )
    )
    policies = list(
        pages(control, "list_policies", "policies", policyEngineId=access["PolicyEngineId"])
    )
    if {p["name"] for p in policies} != set(expected):
        raise ValueError("POLICY_SET_MISMATCH")
    for policy in policies:
        if (
            policy["status"] != "ACTIVE"
            or policy["enforcementMode"] != "ACTIVE"
            or policy["definition"]["cedar"]["statement"].strip()
            != expected[policy["name"]].strip()
        ):
            raise ValueError("PRINCIPAL_BINDING_POLICY_MISMATCH")
    if config.get("auth_provider") == "cognito":
        if not gw.get("workloadIdentityDetails", {}).get("workloadIdentityArn"):
            raise ValueError("GATEWAY_WORKLOAD_IDENTITY_MISSING")
    else:
        provider = control.get_oauth2_credential_provider(name=access["OAuthProviderName"])
        oauth = provider["oauth2ProviderConfigOutput"]["customOauth2ProviderConfig"]
        if (
            provider["credentialProviderArn"] != access["OAuthProviderArn"]
            or oauth["clientId"] != config["broker_client_id"]
            or oauth.get("onBehalfOfTokenExchangeConfig", {}).get("grantType")
            != "JWT_AUTHORIZATION_GRANT"
        ):
            raise ValueError("OBO_PROVIDER_MISMATCH")
    return {**data, **access, "mode": "AWS_READ_ONLY", "invocation_verified": False}
