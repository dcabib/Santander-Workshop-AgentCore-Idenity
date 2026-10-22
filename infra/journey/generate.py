"""CloudFormation do cenário A → central → B → MCP Databricks; geração offline."""

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from infra.banking import generate as banking
from infra.federation.generate import UUID, authorizer
from infra.federation.generate import gateway as federation_gateway
from infra.generate import (
    att,
    bootstrap,
    output,
    param,
    ref,
    resource,
    role,
    statement,
    sub,
    template,
)
from santander_demo.journey.spec import ACCOUNTS, AGENT_SCHEMA, AGENTS, SQL_SCHEMA, cedar, tool_name

ROOT = Path(__file__).resolve().parent
TABLE_PATTERN = r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*"


def gateway(account):
    t = federation_gateway("data")  # sem Guardrail/Bedrock; as provas usam agentes determinísticos.
    t["Description"] = "Santander 12 - " + account + " Gateway, Identity and ENFORCE Policy"
    t["Parameters"]["Project"]["Default"] = "santander-journey"
    if account == "platform":
        del t["Parameters"]["CallerClientId"]
        claims = t["Resources"]["Gateway"]["Properties"]["AuthorizerConfiguration"][
            "CustomJWTAuthorizer"
        ]["CustomClaims"]
        claims[:] = [claim for claim in claims if claim["InboundTokenClaimName"] != "azp"]
        # Os dois azp são autorizados por tool no Cedar, sem união permissiva de callers.
    if account == "data":
        del t["Parameters"]["GatewaySecretArn"]
        t["Parameters"].update(
            {
                "DatabricksHost": param(
                    AllowedPattern=r"https://adb-[0-9]+\.[0-9]+\.azuredatabricks\.net"
                ),
                "DatabricksClientId": param(),
                "DatabricksSecretArn": param(),
            }
        )
        t["Resources"]["OAuth"]["Properties"]["Oauth2ProviderConfigInput"] = {
            "CustomOauth2ProviderConfig": {
                "OauthDiscovery": {
                    "DiscoveryUrl": sub("${DatabricksHost}/oidc/.well-known/openid-configuration")
                },
                "ClientId": ref("DatabricksClientId"),
                "ClientSecretSource": "EXTERNAL",
                "ClientSecretConfig": {
                    "SecretId": ref("DatabricksSecretArn"),
                    "JsonKey": "client_secret",
                },
                # Mesmo shape do sample native-obo; modo público depende de habilitação AWS.
                # Não existe enum NONE em ClientAuthenticationMethod. Não inventar esse campo.
                "OnBehalfOfTokenExchangeConfig": {
                    "GrantType": "TOKEN_EXCHANGE",
                    "TokenExchangeGrantTypeConfig": {"ActorTokenContent": "NONE"},
                },
            },
        }
        permissions = t["Resources"]["GatewayRole"]["Properties"]["Policies"][0]["PolicyDocument"][
            "Statement"
        ]
        for permission in permissions:
            if "secretsmanager:GetSecretValue" in permission["Action"]:
                permission["Resource"] = [
                    ref("DatabricksSecretArn"),
                    sub(
                        "arn:${AWS::Partition}:secretsmanager:*:${AWS::AccountId}:secret:bedrock-agentcore-identity*"
                    ),
                ]
        permissions.append(
            statement(
                ["kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey"],
                "*",
                Condition={
                    "StringEquals": {"kms:CallerAccount": ref("AWS::AccountId")},
                    "StringLike": {"kms:ViaService": "secretsmanager.*.amazonaws.com"},
                },
            )
        )
    return t


def target(name, endpoint, schemas, *, scopes, databricks=False):
    return resource(
        "AWS::BedrockAgentCore::GatewayTarget",
        {
            "GatewayIdentifier": ref("GatewayId"),
            "Name": name,
            "TargetConfiguration": {
                "Mcp": {
                    "McpServer": {
                        "Endpoint": endpoint,
                        # Schema explícito seleciona somente execute_sql e dispensa sync com identidade M2M.
                        "McpToolSchema": {"InlinePayload": json.dumps({"tools": schemas})},
                    }
                }
            },
            "CredentialProviderConfigurations": [
                {
                    "CredentialProviderType": "OAUTH",
                    "CredentialProvider": {
                        "OauthCredentialProvider": {
                            "ProviderArn": ref("OAuthProviderArn"),
                            "Scopes": scopes,
                            "GrantType": "TOKEN_EXCHANGE",
                            "CustomParameters": (
                                {
                                    "requested_token_type": "urn:ietf:params:oauth:token-type:access_token"
                                }
                                if databricks
                                else {"requested_token_use": "on_behalf_of"}
                            ),
                        }
                    },
                }
            ],
        },
    )


def bindings(account):
    params = {
        "GatewayId": param(),
        "GatewayArn": param(),
        "PolicyEngineId": param(),
        "OAuthProviderArn": param(),
        "TenantId": param(AllowedPattern=UUID),
        "AllowedUserOids": param(AllowedPattern=UUID + r"(," + UUID + r")*"),
    }
    if account == "origin":
        params["CallerClientId"] = param(AllowedPattern=UUID)
        for agent in AGENTS:
            params[agent.title() + "Endpoint"] = param()
            params[agent.title() + "ClientId"] = param(AllowedPattern=UUID)
    elif account == "platform":
        params.update(
            {
                "DataEndpoint": param(),
                "DataClientId": param(AllowedPattern=UUID),
                "RiscosClientId": param(AllowedPattern=UUID),
                "FraudeClientId": param(AllowedPattern=UUID),
            }
        )
    else:
        params.update(
            {
                "CallerClientId": param(AllowedPattern=UUID),
                "DatabricksMcpUrl": param(
                    AllowedPattern=r"https://adb-[0-9]+\.[0-9]+\.azuredatabricks\.net/.*"
                ),
                "DatabricksScope": param(
                    "all-apis", AllowedValues=["all-apis", "sql", "ai-gateway"]
                ),
            }
        )
    if account != "origin":
        params.update(
            {agent.title() + "Table": param(AllowedPattern=TABLE_PATTERN) for agent in AGENTS}
        )
    t = template("Santander 12 - " + account + " targets and user/agent/tool policies", params)
    targets = []
    if account == "platform":
        t["Resources"]["DataTarget"] = target(
            "dados",
            ref("DataEndpoint"),
            [{**SQL_SCHEMA, "name": tool_name(agent, "data")} for agent in AGENTS],
            scopes=[sub("api://${DataClientId}/.default")],
        )
        targets = ["DataTarget"]
    else:
        for agent in AGENTS:
            key = agent.title() + "Target"
            t["Resources"][key] = target(
                agent,
                ref("DatabricksMcpUrl") if account == "data" else ref(agent.title() + "Endpoint"),
                [SQL_SCHEMA if account == "data" else AGENT_SCHEMA],
                scopes=[ref("DatabricksScope")]
                if account == "data"
                else [sub("api://${" + agent.title() + "ClientId}/.default")],
                databricks=account == "data",
            )
            targets.append(key)
    callers = {
        "origin": "${CallerClientId}",
        "data": "${CallerClientId}",
        "riscos": "${RiscosClientId}",
        "fraude": "${FraudeClientId}",
    }
    tables = {"riscos": "demo.riscos.canario", "fraude": "demo.fraude.canario"}
    for name, code in cedar(
        account, "${GatewayArn}", "${TenantId}", callers, ["USER_LIST"], tables
    ).items():
        code = code.replace('["USER_LIST"]', '["${UserList}"]')
        for agent in AGENTS:
            code = code.replace(tables[agent], "${" + agent.title() + "Table}")
        t["Resources"][name] = resource(
            "AWS::BedrockAgentCore::Policy",
            {
                "Name": name,
                "PolicyEngineId": ref("PolicyEngineId"),
                "Definition": {
                    "Cedar": {
                        "Statement": {
                            "Fn::Sub": [
                                code,
                                {
                                    "UserList": {
                                        "Fn::Join": [
                                            '", "',
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
    t = banking.bindings()
    t["Description"] = "Santander 12 - catalog ownership, review and cross-account discovery"
    t["Parameters"] = {
        **banking.artifact_params(),
        "Project": param("santander-journey"),
        "GatewayUrl": param(),
        "OriginAccount": param(AllowedPattern=r"[0-9]{12}"),
        "ApproveRecords": param("false", AllowedValues=["false", "true"]),
    }
    t["Conditions"] = {"ApproveRecords": {"Fn::Equals": [ref("ApproveRecords"), "true"]}}
    t["Resources"] = {
        key: value
        for key, value in t["Resources"].items()
        if value["Type"]
        not in {
            "AWS::BedrockAgentCore::GatewayTarget",
            "AWS::BedrockAgentCore::Policy",
            "Custom::AgentCoreRegistryRecord",
            "Custom::AgentCoreRegistryApproval",
        }
    }
    r = t["Resources"]
    for agent in AGENTS:
        server = {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
            "name": "com.santander.demo/" + agent,
            "description": "Santander " + agent + " canary DBSQL",
            "version": "1.0.0",
            "remotes": [{"type": "streamable-http", "url": "${GatewayUrl}"}],
            "_meta": {"com.santander/owner": "dados", "com.santander/instance": "${Project}"},
        }
        key = agent.title() + "Record"
        r[key] = resource(
            "Custom::AgentCoreRegistryRecord",
            {
                "ServiceToken": att("RecordProvider", "Arn"),
                "ServiceTimeout": 650,
                "Kind": "Record",
                "RegistryId": att("Catalog", "Id"),
                "Name": agent,
                "Description": "Santander " + agent + "; owner=dados; instance managed by IaC",
                "Version": "1.0.0",
                "Submit": "true",
                "Descriptors": {
                    "mcp": {
                        "server": {
                            "schemaVersion": "2025-12-11",
                            "inlineContent": sub(json.dumps(server)),
                        },
                        "tools": {
                            "protocolVersion": "2025-11-25",
                            "inlineContent": json.dumps(
                                {
                                    "tools": [{**SQL_SCHEMA, "name": tool_name(agent)}],
                                }
                            ),
                        },
                    }
                },
            },
        )
        r[key + "Approval"] = resource(
            "Custom::AgentCoreRegistryApproval",
            {
                "ServiceToken": att("ApprovalProvider", "Arn"),
                "ServiceTimeout": 650,
                "Kind": "Approval",
                "RegistryId": att("Catalog", "Id"),
                "RecordId": att(key, "Id"),
                "Decision": "APPROVED",
            },
            Condition="ApproveRecords",
        )
    r["ConsumerRole"] = role(
        "unused",
        [
            statement(["bedrock-agentcore:SearchRegistryRecords"], att("Catalog", "Arn")),
        ],
    )
    r["ConsumerRole"]["Properties"].update(
        {
            "RoleName": sub("${Project}-catalog-consumer"),
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "sts:AssumeRole",
                        "Principal": {
                            "AWS": sub("arn:${AWS::Partition}:iam::${OriginAccount}:root")
                        },
                        "Condition": {
                            "ArnEquals": {
                                "aws:PrincipalArn": [
                                    sub(
                                        "arn:${AWS::Partition}:iam::${OriginAccount}:role/${Project}-"
                                        + agent
                                        + "-runtime"
                                    )
                                    for agent in AGENTS
                                ]
                            }
                        },
                    }
                ],
            },
        }
    )
    output(t, "RegistryConsumerRoleArn", att("ConsumerRole", "Arn"))
    return t


def agent_runtime(agent):
    t = template(
        "Santander 12 - " + agent + " hosted deterministic agent, OBO through Identity",
        {
            **banking.artifact_params(),
            "Project": param("santander-journey"),
            "TenantId": param(AllowedPattern=UUID),
            "RuntimeClientId": param(AllowedPattern=UUID),
            "CallerClientId": param(AllowedPattern=UUID),
            "AgentSecretArn": param(),
            "GatewayArn": param(),
            "HubUrl": param(),
            "HubClientId": param(AllowedPattern=UUID),
            "RegistryArn": param(),
            "RegistryConsumerRoleArn": param(),
            "SubjectClaim": param(
                "preferred_username", AllowedValues=["preferred_username", "email", "upn"]
            ),
            **{name.title() + "Table": param(AllowedPattern=TABLE_PATTERN) for name in AGENTS},
        },
    )
    r = t["Resources"]
    r["Workload"] = resource(
        "AWS::BedrockAgentCore::WorkloadIdentity", {"Name": sub("${Project}-" + agent)}
    )
    r["OAuth"] = copy.deepcopy(gateway("origin")["Resources"]["OAuth"])
    p = r["OAuth"]["Properties"]
    p["Name"] = sub("${Project}-" + agent + "-obo")
    p["Oauth2ProviderConfigInput"]["CustomOauth2ProviderConfig"].update(
        {
            "ClientId": ref("RuntimeClientId"),
            "ClientSecretConfig": {"SecretId": ref("AgentSecretArn"), "JsonKey": "client_secret"},
        }
    )
    r["RuntimeRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            banking.artifact_read(),
            banking.runtime_logs(),
            statement(["sts:AssumeRole"], ref("RegistryConsumerRoleArn")),
            statement(
                ["bedrock-agentcore:GetWorkloadAccessTokenForJWT"],
                [
                    att("Workload", "WorkloadIdentityArn"),
                    sub(
                        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/default"
                    ),
                ],
            ),
            statement(
                ["bedrock-agentcore:GetResourceOauth2Token"],
                [
                    att("OAuth", "CredentialProviderArn"),
                    att("Workload", "WorkloadIdentityArn"),
                ],
            ),
            statement(["secretsmanager:GetSecretValue"], ref("AgentSecretArn")),
        ],
    )
    r["RuntimeRole"]["Properties"]["RoleName"] = sub("${Project}-" + agent + "-runtime")
    config = {
        "agent": agent,
        "project": "${Project}",
        "region": "${AWS::Region}",
        "tenant": "${TenantId}",
        "audience": "${RuntimeClientId}",
        "caller": "${CallerClientId}",
        "hub_url": "${HubUrl}",
        "hub_audience": "${HubClientId}",
        "subject_claim": "${SubjectClaim}",
        "workload_name": "${Project}-" + agent,
        "provider_name": "${Project}-" + agent + "-obo",
        "registry_arn": "${RegistryArn}",
        "registry_role_arn": "${RegistryConsumerRoleArn}",
        "tables": {name: "${" + name.title() + "Table}" for name in AGENTS},
    }
    auth = authorizer(ref("RuntimeClientId"))
    auth["AllowedWorkloadConfiguration"] = {"HostingEnvironments": [{"Arn": ref("GatewayArn")}]}
    r["Runtime"] = banking.runtime_resource(sub("${RuntimeName}"), "mcp", {}, auth)
    t["Parameters"]["RuntimeName"] = param(AllowedPattern=r"[A-Za-z][A-Za-z0-9_]*")
    runtime = r["Runtime"]["Properties"]
    runtime["AgentRuntimeArtifact"]["CodeConfiguration"]["EntryPoint"] = [
        "python",
        "journey_runtime_main.py",
    ]
    runtime["EnvironmentVariables"] = {"JOURNEY_CONFIG": sub(json.dumps(config))}
    runtime["RequestHeaderConfiguration"] = {"RequestHeaderAllowlist": ["Authorization"]}
    for name in ("AgentRuntimeArn", "AgentRuntimeId"):
        output(t, name.replace("Agent", ""), att("Runtime", name))
    return t


def generate():
    docs = {"bootstrap": bootstrap(), "registry": registry()}
    for account in ACCOUNTS:
        docs[account + "-gateway"] = gateway(account)
        docs[account + "-bindings"] = bindings(account)
    for agent in AGENTS:
        docs[agent + "-agent"] = agent_runtime(agent)
    directory = ROOT / "templates"
    directory.mkdir(parents=True, exist_ok=True)
    for name, doc in docs.items():
        (directory / (name + ".json")).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        )
    return docs


if __name__ == "__main__":
    print("Templates locais:", ", ".join(generate()))
