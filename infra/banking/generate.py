"""IaC do notebook 11: gera templates locais, sem acessar contas AWS."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
from santander_demo.banking.spec import LOBS, TABLE_KEYS, cedar, data_file

ROOT = Path(__file__).resolve().parent


def okta_client(client):
    # Okta emite cid; AllowedClients compara client_id, uma claim diferente.
    return [
        {
            "InboundTokenClaimName": "cid",
            "InboundTokenClaimValueType": "STRING",
            "AuthorizingClaimMatchValue": {
                "ClaimMatchOperator": "EQUALS",
                "ClaimMatchValue": {"MatchValueString": client},
            },
        }
    ]


def runtime_logs():
    return statement(
        [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:DescribeLogStreams",
            "logs:PutLogEvents",
        ],
        sub(
            "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/*"
        ),
    )


def artifact_read():
    return statement(
        ["s3:GetObject"], sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/${ArtifactKey}")
    )


def artifact_params():
    return {"ArtifactBucket": param(), "ArtifactKey": param()}


def runtime_resource(name, service, environment, authorizer, role_name="RuntimeRole"):
    return resource(
        "AWS::BedrockAgentCore::Runtime",
        {
            "AgentRuntimeName": name,
            "RoleArn": att(role_name, "Arn"),
            "AgentRuntimeArtifact": {
                "CodeConfiguration": {
                    "Runtime": "PYTHON_3_12",
                    "EntryPoint": ["python", "banking_runtime_main.py"],
                    "Code": {"S3": {"Bucket": ref("ArtifactBucket"), "Prefix": ref("ArtifactKey")}},
                }
            },
            "ProtocolConfiguration": "HTTP" if service == "agent" else "MCP",
            "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
            "AuthorizerConfiguration": {"CustomJWTAuthorizer": authorizer},
            "EnvironmentVariables": {"BANKING_SERVICE": service, **environment},
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 300, "MaxLifetime": 3600},
        },
    )


def platform():
    t = template(
        "Notebook 11 - platform Gateway, OAuth M2M, Policy engine, Guardrail",
        {
            "Project": param("banking-demo"),
            "DiscoveryUrl": param(),
            "Audience": param("lobfederation"),
            "UserClientId": param(),
            "M2MClientId": param(),
            "M2MSecretArn": param(),
        },
    )
    r = t["Resources"]
    r["OAuth"] = resource(
        "AWS::BedrockAgentCore::OAuth2CredentialProvider",
        {
            "Name": sub("${Project}-m2m"),
            "CredentialProviderVendor": "CustomOauth2",
            "Oauth2ProviderConfigInput": {
                "CustomOauth2ProviderConfig": {
                    "OauthDiscovery": {"DiscoveryUrl": ref("DiscoveryUrl")},
                    "ClientId": ref("M2MClientId"),
                    "ClientSecretSource": "EXTERNAL",
                    "ClientSecretConfig": {
                        "SecretId": ref("M2MSecretArn"),
                        "JsonKey": "client_secret",
                    },
                    "ClientAuthenticationMethod": "CLIENT_SECRET_BASIC",
                }
            },
        },
    )
    r["GatewayRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            statement(
                ["bedrock-agentcore:GetResourceOauth2Token"], att("OAuth", "CredentialProviderArn")
            ),
            statement(["secretsmanager:GetSecretValue"], ref("M2MSecretArn")),
            statement(
                [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                ],
                [
                    sub(
                        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/default"
                    ),
                    sub(
                        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/default/workload-identity/*"
                    ),
                ],
            ),
        ],
    )
    r["Engine"] = resource("AWS::BedrockAgentCore::PolicyEngine", {"Name": "banking_blog_policy"})
    r["Gateway"] = resource(
        "AWS::BedrockAgentCore::Gateway",
        {
            "Name": ref("Project"),
            "RoleArn": att("GatewayRole", "Arn"),
            "ProtocolType": "MCP",
            "ProtocolConfiguration": {"Mcp": {"SearchType": "SEMANTIC"}},
            "AuthorizerType": "CUSTOM_JWT",
            "AuthorizerConfiguration": {
                "CustomJWTAuthorizer": {
                    "DiscoveryUrl": ref("DiscoveryUrl"),
                    "AllowedAudience": [ref("Audience")],
                    "CustomClaims": okta_client(ref("UserClientId")),
                }
            },
            "PolicyEngineConfiguration": {
                "Arn": att("Engine", "PolicyEngineArn"),
                "Mode": "ENFORCE",
            },
        },
    )
    r["Guardrail"] = resource(
        "AWS::Bedrock::Guardrail",
        {
            "Name": sub("${Project}-guardrail"),
            "BlockedInputMessaging": "Entrada bloqueada pelo guardrail do laboratório.",
            "BlockedOutputsMessaging": "Saída bloqueada pelo guardrail do laboratório.",
            "SensitiveInformationPolicyConfig": {
                "PiiEntitiesConfig": [
                    {"Type": "US_SOCIAL_SECURITY_NUMBER", "Action": "ANONYMIZE"},
                    {"Type": "CREDIT_DEBIT_CARD_NUMBER", "Action": "ANONYMIZE"},
                ]
            },
        },
    )
    r["GuardrailVersion"] = resource(
        "AWS::Bedrock::GuardrailVersion",
        {"GuardrailIdentifier": ref("Guardrail"), "Description": "Notebook 11 - synthetic banking"},
    )
    # Data-plane delivery pertence ao stack; o notebook apenas consulta seu status.
    r["GatewayLog"] = resource(
        "AWS::Logs::LogGroup",
        {"LogGroupName": sub("/aws/vendedlogs/${Project}/gateway"), "RetentionInDays": 7},
    )
    r["GatewayLogSource"] = resource(
        "AWS::Logs::DeliverySource",
        {
            "Name": sub("${Project}-gateway"),
            "LogType": "APPLICATION_LOGS",
            "ResourceArn": att("Gateway", "GatewayArn"),
        },
    )
    r["GatewayLogDestination"] = resource(
        "AWS::Logs::DeliveryDestination",
        {
            "Name": sub("${Project}-gateway"),
            "DestinationResourceArn": att("GatewayLog", "Arn"),
            "OutputFormat": "json",
        },
    )
    r["GatewayLogDelivery"] = resource(
        "AWS::Logs::Delivery",
        {
            "DeliverySourceName": ref("GatewayLogSource"),
            "DeliveryDestinationArn": att("GatewayLogDestination", "Arn"),
        },
    )
    for key, value in {
        "GatewayId": att("Gateway", "GatewayIdentifier"),
        "GatewayArn": att("Gateway", "GatewayArn"),
        "GatewayUrl": att("Gateway", "GatewayUrl"),
        "PolicyEngineId": att("Engine", "PolicyEngineId"),
        "PolicyEngineArn": att("Engine", "PolicyEngineArn"),
        "OAuthProviderArn": att("OAuth", "CredentialProviderArn"),
        "GuardrailId": att("Guardrail", "GuardrailId"),
        "GuardrailVersion": att("GuardrailVersion", "Version"),
        "GatewayLogGroup": ref("GatewayLog"),
    }.items():
        output(t, key, value)
    return t


def lob(name):
    fixtures = data_file("fixtures.json")[name]
    t = template(
        "Notebook 11 - " + name + " MCP and synthetic DynamoDB fixtures",
        {
            **artifact_params(),
            "Project": param("banking-demo"),
            "DiscoveryUrl": param(),
            "Audience": param("lobfederation"),
            "M2MClientId": param(),
            "GatewayArn": param(),
            **(
                {"KnowledgeBaseId": param(AllowedPattern="[A-Za-z0-9]{10}")}
                if name == "lending-wealth"
                else {}
            ),
        },
    )
    r = t["Resources"]
    for table in fixtures:
        pk, sk = TABLE_KEYS[table]
        attributes = [{"AttributeName": pk, "AttributeType": "S"}]
        keys = [{"AttributeName": pk, "KeyType": "HASH"}]
        if sk:
            attributes.append({"AttributeName": sk, "AttributeType": "N"})
            keys.append({"AttributeName": sk, "KeyType": "RANGE"})
        r[table] = resource(
            "AWS::DynamoDB::Table",
            {
                "TableName": sub("${Project}-" + table),
                "BillingMode": "PAY_PER_REQUEST",
                "AttributeDefinitions": attributes,
                "KeySchema": keys,
                "SSESpecification": {"SSEEnabled": True},
                "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
            },
            DeletionPolicy="Retain",
            UpdateReplacePolicy="Retain",
        )
    table_arns = [att(table, "Arn") for table in fixtures]
    runtime_permissions = [
        artifact_read(),
        runtime_logs(),
        statement(["dynamodb:GetItem", "dynamodb:Scan", "dynamodb:Query"], table_arns),
    ]
    environment = {"TABLE_PREFIX": sub("${Project}-")}
    if name == "lending-wealth":
        runtime_permissions.append(
            statement(
                ["bedrock:Retrieve"],
                sub(
                    "arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:knowledge-base/${KnowledgeBaseId}"
                ),
            )
        )
        environment["KNOWLEDGE_BASE_ID"] = ref("KnowledgeBaseId")
    r["RuntimeRole"] = role("bedrock-agentcore.amazonaws.com", runtime_permissions)
    r["SeedLog"] = resource(
        "AWS::Logs::LogGroup",
        {"LogGroupName": sub("${AWS::StackName}-fixtures"), "RetentionInDays": 7},
    )
    r["SeedRole"] = role(
        "lambda.amazonaws.com",
        [
            statement(["dynamodb:PutItem"], table_arns),
            statement(["logs:CreateLogStream", "logs:PutLogEvents"], att("SeedLog", "Arn")),
        ],
    )
    r["SeedProvider"] = resource(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Handler": "banking_seed_handler.handler",
            "Architectures": ["arm64"],
            "MemorySize": 256,
            "Timeout": 300,
            "Role": att("SeedRole", "Arn"),
            "LoggingConfig": {"LogGroup": ref("SeedLog")},
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
        },
    )
    r["Fixtures"] = resource(
        "Custom::BankingFixtures",
        {
            "ServiceToken": att("SeedProvider", "Arn"),
            "Lob": name,
            "Tables": {table: ref(table) for table in fixtures},
            "FixtureVersion": "upstream-f76491b6",
        },
        DeletionPolicy="Retain",
        UpdateReplacePolicy="Retain",
    )
    r["Runtime"] = runtime_resource(
        "banking_" + LOBS[name]["module"],
        name,
        environment,
        {
            "DiscoveryUrl": ref("DiscoveryUrl"),
            "AllowedAudience": [ref("Audience")],
            "CustomClaims": okta_client(ref("M2MClientId")),
            "AllowedWorkloadConfiguration": {"HostingEnvironments": [{"Arn": ref("GatewayArn")}]},
        },
    )
    r["Runtime"]["DependsOn"] = ["Fixtures"]
    output(t, "RuntimeArn", att("Runtime", "AgentRuntimeArn"))
    output(t, "RuntimeId", att("Runtime", "AgentRuntimeId"))
    output(t, "TablePrefix", sub("${Project}-"))
    if name == "lending-wealth":
        output(t, "KnowledgeBaseId", ref("KnowledgeBaseId"))
    return t


def bindings():
    t = template(
        "Notebook 11 - targets M2M, active Cedar, governed Registry",
        {
            **artifact_params(),
            "Project": param("banking-demo"),
            "GatewayId": param(),
            "GatewayArn": param(),
            "GatewayUrl": param(),
            "PolicyEngineId": param(),
            "OAuthProviderArn": param(),
            "Scope": param("lobfederation.invoke"),
            **{LOBS[lob]["module"].title() + "Endpoint": param() for lob in LOBS},
        },
    )
    r = t["Resources"]
    schemas = data_file("tools.json")
    targets = []
    for lob_name, config in LOBS.items():
        logical = config["module"].title() + "Target"
        targets.append(logical)
        r[logical] = resource(
            "AWS::BedrockAgentCore::GatewayTarget",
            {
                "GatewayIdentifier": ref("GatewayId"),
                "Name": lob_name,
                "Description": config["description"],
                "TargetConfiguration": {
                    "Mcp": {
                        "McpServer": {
                            "Endpoint": ref(config["module"].title() + "Endpoint"),
                            "McpToolSchema": {
                                "InlinePayload": json.dumps({"tools": schemas[lob_name]})
                            },
                        }
                    }
                },
                "CredentialProviderConfigurations": [
                    {
                        "CredentialProviderType": "OAUTH",
                        "CredentialProvider": {
                            "OauthCredentialProvider": {
                                "ProviderArn": ref("OAuthProviderArn"),
                                "Scopes": [ref("Scope")],
                                "GrantType": "CLIENT_CREDENTIALS",
                            }
                        },
                    }
                ],
            },
        )
    # Read-only walkthrough; write tools retain their upstream schemas but get no permit.
    for name, code in cedar("${GatewayArn}").items():
        if name == "WriteTools":
            continue
        r[name] = resource(
            "AWS::BedrockAgentCore::Policy",
            {
                "Name": "Banking" + name,
                "PolicyEngineId": ref("PolicyEngineId"),
                "Definition": {"Cedar": {"Statement": sub(code)}},
                "ValidationMode": "FAIL_ON_ANY_FINDINGS",
                "EnforcementMode": "ACTIVE",
            },
            DependsOn=targets,
        )
    operations = {
        "Registry": ["CreateRegistry", "GetRegistry", "DeleteRegistry"],
        "Record": [
            "CreateRegistryRecord",
            "GetRegistryRecord",
            "DeleteRegistryRecord",
            "SubmitRegistryRecordForApproval",
        ],
        "Approval": ["GetRegistryRecord", "UpdateRegistryRecordStatus"],
    }
    for kind, ops in operations.items():
        log = kind + "Log"
        r[log] = resource(
            "AWS::Logs::LogGroup",
            {"LogGroupName": sub("${AWS::StackName}-" + kind.lower()), "RetentionInDays": 7},
        )
        r[kind + "Role"] = role(
            "lambda.amazonaws.com",
            [
                statement(["logs:CreateLogStream", "logs:PutLogEvents"], att(log, "Arn")),
                statement(
                    ["bedrock-agentcore:" + op for op in ops if op != "CreateRegistry"],
                    [
                        sub(
                            "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:registry/*"
                        ),
                        sub(
                            "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:registry/*/record/*"
                        ),
                    ],
                ),
                *(
                    [
                        # CreateRegistry não aceita resource-level IAM, conforme
                        # Service Authorization Reference. Get/Delete seguem por ARN.
                        statement(
                            ["bedrock-agentcore:CreateRegistry"],
                            "*",
                            Condition={"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}},
                        )
                    ]
                    if kind == "Registry"
                    else []
                ),
            ],
        )
        r[kind + "Provider"] = resource(
            "AWS::Lambda::Function",
            {
                "Runtime": "python3.12",
                "Handler": "registry_handler.handler",
                "Architectures": ["arm64"],
                "MemorySize": 256,
                "Timeout": 600,
                "Role": att(kind + "Role", "Arn"),
                "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
                "LoggingConfig": {"LogGroup": ref(log)},
                "Environment": {"Variables": {"RESOURCE_KIND": kind}},
            },
        )
    r["Catalog"] = resource(
        "Custom::AgentCoreRegistry",
        {
            "ServiceToken": att("RegistryProvider", "Arn"),
            "ServiceTimeout": 650,
            "Kind": "Registry",
            "Name": ref("Project"),
        },
    )
    for lob_name, config in LOBS.items():
        name = config["module"].title() + "Record"
        tools = [{**tool, "name": lob_name + "___" + tool["name"]} for tool in schemas[lob_name]]
        server = {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
            "name": "com.santander.banking/" + lob_name,
            "description": config["description"],
            "version": "1.0.0",
            "remotes": [{"type": "streamable-http", "url": "${GatewayUrl}"}],
        }
        r[name] = resource(
            "Custom::AgentCoreRegistryRecord",
            {
                "ServiceToken": att("RecordProvider", "Arn"),
                "ServiceTimeout": 650,
                "Kind": "Record",
                "RegistryId": att("Catalog", "Id"),
                "Name": lob_name,
                "Description": config["description"],
                "Version": "1.0",
                "Submit": "true",
                "Descriptors": {
                    "mcp": {
                        "server": {
                            "schemaVersion": "2025-12-11",
                            "inlineContent": sub(json.dumps(server)),
                        },
                        "tools": {
                            "protocolVersion": "2025-11-25",
                            "inlineContent": json.dumps({"tools": tools}),
                        },
                    }
                },
            },
        )
        r[name + "Approval"] = resource(
            "Custom::AgentCoreRegistryApproval",
            {
                "ServiceToken": att("ApprovalProvider", "Arn"),
                "ServiceTimeout": 650,
                "Kind": "Approval",
                "RegistryId": att("Catalog", "Id"),
                "RecordId": att(name, "Id"),
                "Decision": "APPROVED",
            },
        )
    output(t, "RegistryArn", att("Catalog", "Arn"))
    output(t, "RegistryId", att("Catalog", "Id"))
    return t


def agent():
    t = template(
        "Notebook 11 - Strands agent hosted in platform Runtime",
        {
            **artifact_params(),
            "DiscoveryUrl": param(),
            "Audience": param("lobfederation"),
            "UserClientId": param(),
            "GatewayUrl": param(),
            "RegistryArn": param(),
            "GuardrailId": param(),
            "GuardrailVersion": param(),
            "ModelId": param("us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            "ModelResourceArns": {
                "Type": "CommaDelimitedList",
                "Description": "Exact inference-profile and destination foundation-model ARNs for the selected model",
            },
        },
    )
    r = t["Resources"]
    r["RuntimeRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            artifact_read(),
            runtime_logs(),
            statement(
                ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                ref("ModelResourceArns"),
            ),
            statement(
                ["bedrock-agentcore:SearchRegistryRecords"],
                [ref("RegistryArn"), sub("${RegistryArn}/record/*")],
            ),
            statement(
                ["bedrock:ApplyGuardrail"],
                sub(
                    "arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:guardrail/${GuardrailId}"
                ),
            ),
        ],
    )
    config = {
        "region": "${AWS::Region}",
        "gateway_url": "${GatewayUrl}",
        "registry_arn": "${RegistryArn}",
        "guardrail_id": "${GuardrailId}",
        "guardrail_version": "${GuardrailVersion}",
        "model_id": "${ModelId}",
    }
    r["Runtime"] = runtime_resource(
        "banking_platform_agent",
        "agent",
        {"BANKING_CONFIG": sub(json.dumps(config))},
        {
            "DiscoveryUrl": ref("DiscoveryUrl"),
            "AllowedAudience": [ref("Audience")],
            "CustomClaims": okta_client(ref("UserClientId")),
        },
    )
    r["Runtime"]["Properties"]["RequestHeaderConfiguration"] = {
        "RequestHeaderAllowlist": ["Authorization"]
    }
    output(t, "AgentRuntimeArn", att("Runtime", "AgentRuntimeArn"))
    return t


def generate():
    templates = {
        "bootstrap": bootstrap(),
        "platform": platform(),
        "bindings": bindings(),
        "agent": agent(),
    }
    templates.update({lob_name: lob(lob_name) for lob_name in LOBS})
    target = ROOT / "templates"
    target.mkdir(exist_ok=True)
    for name, doc in templates.items():
        (target / f"{name}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return templates


if __name__ == "__main__":
    print("Templates locais:", ", ".join(generate()))
