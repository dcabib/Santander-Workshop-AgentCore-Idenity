"""IaC do notebook 12: quatro Gateways, quatro Identity providers e quatro engines."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from infra.banking import generate as banking
from infra.generate import bootstrap, output, param, ref, resource, sub, template
from santander_demo.banking.spec import LOBS
from santander_demo.federation.spec import (
    ACCOUNTS,
    PREFIXES,
    SCOPE,
    cedar,
    local_name,
    schemas,
    tools_by_lob,
)

ROOT = Path(__file__).resolve().parent
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


def claim(name, value):
    return {
        "InboundTokenClaimName": name,
        "InboundTokenClaimValueType": "STRING",
        "AuthorizingClaimMatchValue": {
            "ClaimMatchOperator": "EQUALS",
            "ClaimMatchValue": {"MatchValueString": value},
        },
    }


def authorizer(audience):
    return {
        "DiscoveryUrl": sub(
            "https://login.microsoftonline.com/${TenantId}/v2.0/.well-known/openid-configuration"
        ),
        "AllowedAudience": [audience],
        # Entra v2 emite azp; AllowedClients verifica client_id, não azp.
        "CustomClaims": [
            claim("tid", ref("TenantId")),
            claim("azp", ref("CallerClientId")),
            claim("ver", "2.0"),
            claim("scp", SCOPE),
        ],
    }


def gateway(account):
    t = banking.platform()
    t["Description"] = "Notebook 12 - " + account + " Gateway + Identity OBO + local Policy"
    t["Parameters"] = {
        "Project": param("santander-fed"),
        "TenantId": param(AllowedPattern=UUID),
        "GatewayClientId": param(AllowedPattern=UUID),
        "CallerClientId": param(AllowedPattern=UUID),
        "GatewaySecretArn": param(),
        "EngineName": param(AllowedPattern=r"[A-Za-z][A-Za-z0-9_]*"),
    }
    r = t["Resources"]
    provider = r["OAuth"]["Properties"]
    provider["Name"] = sub("${Project}-obo")
    provider["Oauth2ProviderConfigInput"]["CustomOauth2ProviderConfig"] = {
        "OauthDiscovery": {"DiscoveryUrl": authorizer(ref("GatewayClientId"))["DiscoveryUrl"]},
        "ClientId": ref("GatewayClientId"),
        "ClientSecretSource": "EXTERNAL",
        "ClientSecretConfig": {"SecretId": ref("GatewaySecretArn"), "JsonKey": "client_secret"},
        "ClientAuthenticationMethod": "CLIENT_SECRET_POST",
        "OnBehalfOfTokenExchangeConfig": {"GrantType": "JWT_AUTHORIZATION_GRANT"},
    }
    statements = r["GatewayRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    for statement in statements:
        if "secretsmanager:GetSecretValue" in statement["Action"]:
            statement["Resource"] = ref("GatewaySecretArn")
    r["Engine"]["Properties"]["Name"] = ref("EngineName")
    r["Gateway"]["Properties"]["AuthorizerConfiguration"] = {
        "CustomJWTAuthorizer": authorizer(ref("GatewayClientId"))
    }
    if account != "platform":
        for name in ("Guardrail", "GuardrailVersion"):
            del r[name]
        for name in ("GuardrailId", "GuardrailVersion"):
            del t["Outputs"][name]
    return t


def backend(lob):
    t = banking.lob(lob)
    t["Description"] = "Notebook 12 - " + lob + " MCP accessible through its own Gateway"
    for key in ("DiscoveryUrl", "Audience", "M2MClientId"):
        del t["Parameters"][key]
    t["Parameters"].update(
        {
            "TenantId": param(AllowedPattern=UUID),
            "RuntimeClientId": param(AllowedPattern=UUID),
            "CallerClientId": param(AllowedPattern=UUID),
            "RuntimeName": param(AllowedPattern=r"[A-Za-z][A-Za-z0-9_]*"),
        }
    )
    runtime = t["Resources"]["Runtime"]["Properties"]
    runtime["AgentRuntimeName"] = ref("RuntimeName")
    auth = authorizer(ref("RuntimeClientId"))
    auth["AllowedWorkloadConfiguration"] = {"HostingEnvironments": [{"Arn": ref("GatewayArn")}]}
    runtime["AuthorizerConfiguration"] = {"CustomJWTAuthorizer": auth}
    runtime["RequestHeaderConfiguration"] = {"RequestHeaderAllowlist": ["Authorization"]}
    runtime["EnvironmentVariables"]["FEDERATED_IDENTITY"] = sub(
        json.dumps(
            {
                "tenant": "${TenantId}",
                "audience": "${RuntimeClientId}",
                "caller": "${CallerClientId}",
                "lob": lob,
            }
        )
    )
    return t


def binding(account):
    central = account == "platform"
    params = {
        "GatewayId": param(),
        "GatewayArn": param(),
        "PolicyEngineId": param(),
        "OAuthProviderArn": param(),
        "TenantId": param(AllowedPattern=UUID),
        "CallerClientId": param(AllowedPattern=UUID),
        # UUIDs substituídos somente dentro de literais já delimitados em Cedar.
        "AllowedUserOids": param(AllowedPattern=UUID + r"(," + UUID + r")*"),
    }
    destinations = LOBS if central else {account: LOBS[account]}
    for lob in destinations:
        prefix = PREFIXES[lob].title()
        params[prefix + "Endpoint"] = param()
        params[prefix + "Scope"] = param()
    t = template("Notebook 12 - " + account + " targets OBO and independent Cedar", params)
    targets = []
    for lob in destinations:
        prefix = PREFIXES[lob].title()
        name = prefix + "Target"
        targets.append(name)
        tools = schemas(lob)
        if central:
            tools = [{**tool, "name": local_name(tool["name"])} for tool in tools]
        t["Resources"][name] = resource(
            "AWS::BedrockAgentCore::GatewayTarget",
            {
                "GatewayIdentifier": ref("GatewayId"),
                "Name": PREFIXES[lob] if central else "backend",
                "Description": "OBO to " + (lob + " Gateway" if central else "local MCP Runtime"),
                "TargetConfiguration": {
                    "Mcp": {
                        "McpServer": {
                            "Endpoint": ref(prefix + "Endpoint"),
                            # Schema estático: criação não requer token humano nem fallback M2M.
                            "McpToolSchema": {"InlinePayload": json.dumps({"tools": tools})},
                        }
                    }
                },
                "CredentialProviderConfigurations": [
                    {
                        "CredentialProviderType": "OAUTH",
                        "CredentialProvider": {
                            "OauthCredentialProvider": {
                                "ProviderArn": ref("OAuthProviderArn"),
                                "Scopes": [ref(prefix + "Scope")],
                                "GrantType": "TOKEN_EXCHANGE",
                                "CustomParameters": {"requested_token_use": "on_behalf_of"},
                            }
                        },
                    }
                ],
            },
        )
    policies = cedar(account, "${GatewayArn}", "${TenantId}", "${CallerClientId}", ["USER_LIST"])
    for name, statement in policies.items():
        statement = statement.replace('["USER_LIST"]', '["${UserList}"]')
        t["Resources"][name] = resource(
            "AWS::BedrockAgentCore::Policy",
            {
                "Name": name,
                "PolicyEngineId": ref("PolicyEngineId"),
                "Definition": {
                    "Cedar": {
                        "Statement": {
                            "Fn::Sub": [
                                statement,
                                {
                                    "UserList": {
                                        "Fn::Join": [
                                            '","',
                                            {"Fn::Split": [",", ref("AllowedUserOids")]},
                                        ]
                                    }
                                },
                            ]
                        }
                    }
                },
                "ValidationMode": "FAIL_ON_ANY_FINDINGS",
                "EnforcementMode": "ACTIVE",
            },
            DependsOn=targets,
        )
    return t


def registry():
    # Reutiliza apenas o provider CloudFormation; targets/policies são stacks independentes.
    t = banking.bindings()
    t["Description"] = "Notebook 12 - approved metadata for the federated platform entry point"
    t["Parameters"] = {
        **banking.artifact_params(),
        "Project": param("santander-fed"),
        "GatewayUrl": param(),
    }
    t["Resources"] = {
        key: value
        for key, value in t["Resources"].items()
        if value["Type"]
        not in {"AWS::BedrockAgentCore::GatewayTarget", "AWS::BedrockAgentCore::Policy"}
    }
    for lob in LOBS:
        record = t["Resources"][PREFIXES[lob].title() + "Record"]["Properties"]
        tools = [{**tool, "name": tools_by_lob()[lob][i]} for i, tool in enumerate(schemas(lob))]
        record["Descriptors"]["mcp"]["tools"]["inlineContent"] = json.dumps({"tools": tools})
    output(t, "GatewayUrl", ref("GatewayUrl"))
    return t


def generate():
    templates = {"bootstrap": bootstrap(), "registry": registry()}
    for account in ACCOUNTS:
        templates[account + "-gateway"] = gateway(account)
        templates[account + "-bindings"] = binding(account)
    for lob in LOBS:
        templates[lob + "-backend"] = backend(lob)
    target = ROOT / "templates"
    target.mkdir(parents=True, exist_ok=True)
    for name, doc in templates.items():
        (target / (name + ".json")).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return templates


if __name__ == "__main__":
    print("Templates locais:", ", ".join(generate()))
