"""Gera templates CloudFormation locais. Não usa credenciais nem chama APIs AWS."""

import json
from pathlib import Path

from santander_demo.contracts import TOOLS, tool_descriptors
from santander_demo.policy import PolicyContract, statements

ROOT = Path(__file__).resolve().parent


def ref(name):
    return {"Ref": name}


def att(name, key):
    return {"Fn::GetAtt": [name, key]}


def sub(text):
    return {"Fn::Sub": text}


def param(default=None, **extra):
    return {"Type": "String", **({"Default": default} if default is not None else {}), **extra}


def template(description, parameters=None):
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": description,
        "Parameters": parameters or {},
        "Resources": {},
        "Outputs": {},
    }


def resource(kind, properties, **extra):
    return {"Type": kind, "Properties": properties, **extra}


def statement(actions, resources, **extra):
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def role(service, statements_, name=None):
    props = {
        "AssumeRolePolicyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": service},
                    "Action": "sts:AssumeRole",
                }
            ],
        },
        "Policies": [
            {
                "PolicyName": "workshop",
                "PolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": statements_,
                },
            }
        ],
    }
    if name:
        props["RoleName"] = name
    return resource("AWS::IAM::Role", props)


def logs_policy():
    return statement(
        ["logs:CreateLogStream", "logs:PutLogEvents"],
        [
            sub(
                "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/*:log-stream:*"
            ),
        ],
    )


def output(t, key, value):
    t["Outputs"][key] = {"Value": value}


def bootstrap():
    t = template("Santander - bucket de artefatos gerenciado por IaC")
    t["Resources"]["Artifacts"] = resource(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
                    }
                ]
            },
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
        DeletionPolicy="Retain",
        UpdateReplacePolicy="Retain",
    )
    t["Resources"]["TLSOnly"] = resource(
        "AWS::S3::BucketPolicy",
        {
            "Bucket": ref("Artifacts"),
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [att("Artifacts", "Arn"), sub("${Artifacts.Arn}/*")],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    }
                ],
            },
        },
    )
    output(t, "ArtifactBucket", ref("Artifacts"))
    return t


def hub():
    params = {
        "Project": param("santander-demo", AllowedPattern="[a-z][a-z0-9-]{2,30}"),
        "ArtifactBucket": param(),
        "LambdaKey": param(),
        "TenantId": param(),
        "DiscoveryUrl": param(),
        "GatewayAudience": param(),
        "CallerClaim": param("azp", AllowedValues=["azp", "appid"]),
        "RisksUserOid": param(),
        "BothUserOid": param(),
        "NoGrantUserOid": param(),
        "SupervisorClientId": param(),
        "RisksClientId": param(),
        "FraudClientId": param(),
        "GatewayClientId": param(),
        "EntraSecretArn": param(),
        "FraudEndpoint": param(""),
        "FraudScope": param(""),
        "EnableFraud": param("false", AllowedValues=["true", "false"]),
    }
    for key in [
        "TenantId",
        "RisksUserOid",
        "BothUserOid",
        "NoGrantUserOid",
        "SupervisorClientId",
        "RisksClientId",
        "FraudClientId",
        "GatewayClientId",
    ]:
        params[key]["AllowedPattern"] = "[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
    t = template("Santander - Gateway, Identity OBO e Policy nativos", params)
    r = t["Resources"]
    t["Conditions"] = {"HasFraud": {"Fn::Equals": [ref("EnableFraud"), "true"]}}
    r["RisksLog"] = resource(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/lambda/${Project}-riscos"),
            "RetentionInDays": 7,
        },
    )
    r["RisksRole"] = role("lambda.amazonaws.com", [logs_policy()])
    r["Risks"] = resource(
        "AWS::Lambda::Function",
        {
            "FunctionName": sub("${Project}-riscos"),
            "Runtime": "python3.12",
            "Handler": "santander_demo.backends.lambda_handler",
            "Timeout": 30,
            "MemorySize": 256,
            "Architectures": ["arm64"],
            "Role": att("RisksRole", "Arn"),
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("LambdaKey")},
        },
        DependsOn="RisksLog",
    )
    r["OboProvider"] = resource(
        "AWS::BedrockAgentCore::OAuth2CredentialProvider",
        {
            "Name": sub("${Project}-entra-obo"),
            "CredentialProviderVendor": "CustomOauth2",
            "Oauth2ProviderConfigInput": {
                "CustomOauth2ProviderConfig": {
                    "OauthDiscovery": {
                        "DiscoveryUrl": sub(
                            "https://login.microsoftonline.com/${TenantId}/v2.0/.well-known/openid-configuration"
                        )
                    },
                    "ClientId": ref("GatewayClientId"),
                    "ClientSecretSource": "EXTERNAL",
                    "ClientSecretConfig": {
                        "SecretId": ref("EntraSecretArn"),
                        "JsonKey": "client_secret",
                    },
                    "ClientAuthenticationMethod": "CLIENT_SECRET_POST",
                    "OnBehalfOfTokenExchangeConfig": {"GrantType": "JWT_AUTHORIZATION_GRANT"},
                }
            },
        },
    )
    r["GatewayRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            statement(["lambda:InvokeFunction"], att("Risks", "Arn")),
            statement(
                ["bedrock-agentcore:GetResourceOauth2Token"],
                att("OboProvider", "CredentialProviderArn"),
            ),
            statement(
                ["secretsmanager:GetSecretValue"],
                [
                    ref("EntraSecretArn"),
                ],
            ),
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
    r["PolicyEngine"] = resource(
        "AWS::BedrockAgentCore::PolicyEngine",
        {
            "Name": "santander_policy",
            "Description": "Regras do workshop Santander",
        },
    )
    r["Gateway"] = resource(
        "AWS::BedrockAgentCore::Gateway",
        {
            "Name": ref("Project"),
            "RoleArn": att("GatewayRole", "Arn"),
            "ProtocolType": "MCP",
            "AuthorizerType": "CUSTOM_JWT",
            "AuthorizerConfiguration": {
                "CustomJWTAuthorizer": {
                    "DiscoveryUrl": ref("DiscoveryUrl"),
                    "AllowedAudience": [ref("GatewayAudience")],
                }
            },
            "PolicyEngineConfiguration": {
                "Arn": att("PolicyEngine", "PolicyEngineArn"),
                "Mode": "ENFORCE",
            },
            "ProtocolConfiguration": {"Mcp": {"SearchType": "SEMANTIC"}},
        },
    )
    schema = {
        "Type": "object",
        "Required": ["cliente_id", "max_registros"],
        "Properties": {"cliente_id": {"Type": "string"}, "max_registros": {"Type": "integer"}},
    }
    r["RisksTarget"] = resource(
        "AWS::BedrockAgentCore::GatewayTarget",
        {
            "Name": "riscos",
            "GatewayIdentifier": att("Gateway", "GatewayIdentifier"),
            "TargetConfiguration": {
                "Mcp": {
                    "Lambda": {
                        "LambdaArn": att("Risks", "Arn"),
                        "ToolSchema": {
                            "InlinePayload": [
                                {
                                    "Name": name.split("___")[1],
                                    "Description": spec["description"],
                                    "InputSchema": schema,
                                }
                                for name, spec in TOOLS.items()
                                if spec["domain"] == "riscos"
                            ]
                        },
                    }
                }
            },
            "CredentialProviderConfigurations": [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}],
        },
    )

    def oauth(scopes):
        return [
            {
                "CredentialProviderType": "OAUTH",
                "CredentialProvider": {
                    "OauthCredentialProvider": {
                        "ProviderArn": att("OboProvider", "CredentialProviderArn"),
                        "Scopes": scopes,
                        "GrantType": "TOKEN_EXCHANGE",
                        "CustomParameters": {"requested_token_use": "on_behalf_of"},
                    },
                },
            }
        ]

    graph = {
        "openapi": "3.0.0",
        "info": {"title": "Perfil de teste OBO", "version": "1.0"},
        "servers": [{"url": "https://graph.microsoft.com/v1.0"}],
        "paths": {
            "/me": {
                "get": {
                    "operationId": "getMyProfile",
                    "responses": {"200": {"description": "Perfil do usuário"}},
                }
            }
        },
    }
    r["GraphTarget"] = resource(
        "AWS::BedrockAgentCore::GatewayTarget",
        {
            "Name": "graph",
            "GatewayIdentifier": att("Gateway", "GatewayIdentifier"),
            "TargetConfiguration": {"Mcp": {"OpenApiSchema": {"InlinePayload": json.dumps(graph)}}},
            "CredentialProviderConfigurations": oauth(["https://graph.microsoft.com/.default"]),
        },
    )
    r["FraudTarget"] = resource(
        "AWS::BedrockAgentCore::GatewayTarget",
        {
            "Name": "fraude",
            "GatewayIdentifier": att("Gateway", "GatewayIdentifier"),
            "TargetConfiguration": {
                "Mcp": {
                    "McpServer": {
                        "Endpoint": ref("FraudEndpoint"),
                        "ListingMode": "DEFAULT",
                        # OBO não tem usuário durante a criação. Schema fornecido por IaC evita
                        # sincronização com credencial M2M mais privilegiada.
                        "McpToolSchema": {
                            "InlinePayload": json.dumps(
                                {
                                    "tools": [
                                        {**d, "name": d["name"].split("___")[1]}
                                        for d in tool_descriptors()
                                        if d["name"].startswith("fraude___")
                                    ]
                                }
                            )
                        },
                    }
                }
            },
            "CredentialProviderConfigurations": oauth([ref("FraudScope")]),
            "MetadataConfiguration": {
                "AllowedRequestHeaders": ["Mcp-Session-Id"],
                "AllowedResponseHeaders": ["Mcp-Session-Id"],
            },
        },
        Condition="HasFraud",
    )
    contract = PolicyContract(
        gateway_arn="${Gateway.GatewayArn}",
        tenant="${TenantId}",
        caller_claim="azp",
        risks_users=("${RisksUserOid}", "${BothUserOid}", "${NoGrantUserOid}"),
        fraud_users=("${BothUserOid}",),
        risks_callers=("${SupervisorClientId}", "${RisksClientId}"),
        fraud_callers=("${SupervisorClientId}", "${FraudClientId}"),
    )
    for index, (tool, cedar) in enumerate(statements(contract).items()):
        fraud = tool.startswith("fraude")
        r[f"ToolPolicy{index}"] = resource(
            "AWS::BedrockAgentCore::Policy",
            {
                "Name": f"san_tool_{index}",
                "PolicyEngineId": att("PolicyEngine", "PolicyEngineId"),
                "Definition": {
                    "Cedar": {"Statement": sub(cedar.replace('"azp"', '"${CallerClaim}"'))}
                },
                "ValidationMode": "FAIL_ON_ANY_FINDINGS",
            },
            DependsOn="FraudTarget" if fraud else "RisksTarget",
            **({"Condition": "HasFraud"} if fraud else {}),
        )
    graph_cedar = """permit(principal, action == AgentCore::Action::"graph___getMyProfile",
 resource == AgentCore::Gateway::"${Gateway.GatewayArn}")
when { principal.hasTag("tid") && principal.getTag("tid") == "${TenantId}" &&
 principal.hasTag("oid") && ["${RisksUserOid}", "${BothUserOid}", "${NoGrantUserOid}"].contains(principal.getTag("oid")) &&
 principal.hasTag("${CallerClaim}") && principal.getTag("${CallerClaim}") == "${SupervisorClientId}" &&
 principal.hasTag("scp") };"""
    r["GraphPolicy"] = resource(
        "AWS::BedrockAgentCore::Policy",
        {
            "Name": "san_graph_profile",
            "PolicyEngineId": att("PolicyEngine", "PolicyEngineId"),
            "Definition": {"Cedar": {"Statement": sub(graph_cedar)}},
            "ValidationMode": "FAIL_ON_ANY_FINDINGS",
        },
        DependsOn="GraphTarget",
    )
    r["GatewayLog"] = resource(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/vendedlogs/bedrock-agentcore/${Project}"),
            "RetentionInDays": 7,
        },
    )
    r["GatewayLogSource"] = resource(
        "AWS::Logs::DeliverySource",
        {
            "Name": sub("${Project}-gateway-source"),
            "LogType": "APPLICATION_LOGS",
            "ResourceArn": att("Gateway", "GatewayArn"),
        },
    )
    r["GatewayLogDestination"] = resource(
        "AWS::Logs::DeliveryDestination",
        {
            "Name": sub("${Project}-gateway-destination"),
            "DestinationResourceArn": att("GatewayLog", "Arn"),
            "OutputFormat": "json",
        },
    )
    r["GatewayLogDelivery"] = resource(
        "AWS::Logs::Delivery",
        {
            "DeliverySourceName": ref("GatewayLogSource"),
            "DeliveryDestinationArn": att("GatewayLogDestination", "Arn"),
            "RecordFields": [
                "resource_arn",
                "event_timestamp",
                "body",
                "account_id",
                "timestamp",
                "trace_id",
                "span_id",
                "request_id",
                "gateway_id",
            ],
        },
    )
    for key, value in {
        "GatewayId": att("Gateway", "GatewayIdentifier"),
        "GatewayArn": att("Gateway", "GatewayArn"),
        "GatewayUrl": att("Gateway", "GatewayUrl"),
        "PolicyEngineId": att("PolicyEngine", "PolicyEngineId"),
        "PolicyEngineArn": att("PolicyEngine", "PolicyEngineArn"),
        "OboProviderArn": att("OboProvider", "CredentialProviderArn"),
        "RisksLogGroup": ref("RisksLog"),
        "GatewayLogGroup": ref("GatewayLog"),
    }.items():
        output(t, key, value)
    return t


def catalog():
    t = template(
        "Santander - Registry com providers IaC e papéis separados",
        {
            "Project": param("santander-demo"),
            "ArtifactBucket": param(),
            "ProviderKey": param(),
            "GatewayUrl": param(),
            "OperatorRoleArn": param(),
            "SupervisorRoleArn": param(),
        },
    )
    r = t["Resources"]
    registry_scope = sub(
        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:registry/*"
    )
    records_scope = sub(
        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:registry/*/record/*"
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
        r[kind + "ProviderRole"] = role(
            "lambda.amazonaws.com",
            [
                logs_policy(),
                statement(
                    ["bedrock-agentcore:" + op for op in ops], [registry_scope, records_scope]
                ),
            ],
        )
        r[kind + "ProviderLog"] = resource(
            "AWS::Logs::LogGroup",
            {
                "LogGroupName": sub("/aws/lambda/${Project}-" + kind.lower() + "-provider"),
                "RetentionInDays": 7,
            },
        )
        r[kind + "Provider"] = resource(
            "AWS::Lambda::Function",
            {
                "FunctionName": sub("${Project}-" + kind.lower() + "-provider"),
                "Runtime": "python3.12",
                "Handler": "registry_handler.handler",
                "Timeout": 600,
                "MemorySize": 256,
                "Architectures": ["arm64"],
                "Role": att(kind + "ProviderRole", "Arn"),
                "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ProviderKey")},
                "Environment": {"Variables": {"RESOURCE_KIND": kind}},
            },
            DependsOn=kind + "ProviderLog",
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
    roles = {
        "Publisher": [
            "GetRegistry",
            "ListRegistryRecords",
            "CreateRegistryRecord",
            "GetRegistryRecord",
            "SubmitRegistryRecordForApproval",
        ],
        "Approver": [
            "GetRegistry",
            "ListRegistryRecords",
            "GetRegistryRecord",
            "UpdateRegistryRecordStatus",
        ],
        "Consumer": ["GetRegistry", "GetRegistryRecord", "SearchRegistryRecords"],
    }
    for name, actions in roles.items():
        principal = [ref("OperatorRoleArn")]
        if name == "Consumer":
            principal.append(ref("SupervisorRoleArn"))
        r[name + "Role"] = resource(
            "AWS::IAM::Role",
            {
                "RoleName": sub("${Project}-registry-" + name.lower()),
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": principal},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "Policies": [
                    {
                        "PolicyName": name,
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                statement(
                                    ["bedrock-agentcore:" + op for op in actions],
                                    [att("Catalog", "Arn"), sub("${Catalog.Arn}/record/*")],
                                ),
                            ],
                        },
                    }
                ],
            },
        )
        output(t, name + "RoleArn", att(name + "Role", "Arn"))
    for index, desc in enumerate(tool_descriptors()):
        name = f"Capability{index}"
        server = {
            "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
            "name": "com.santander.demo/" + desc["name"].split("___")[1],
            "description": desc["description"],
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
                "Name": "san-" + desc["name"].replace("_", "-"),
                "Description": desc["description"],
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
                            "inlineContent": json.dumps({"tools": [desc]}),
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
    # Estados visíveis no notebook sem mudar recursos durante a apresentação.
    for name, submit, decision in [
        ("DraftExample", "false", None),
        ("PendingExample", "true", None),
        ("RejectedExample", "true", "REJECTED"),
    ]:
        props = dict(r["Capability0"]["Properties"])
        props.update(
            {"Name": name.lower(), "Submit": submit, "Description": "Fixture de governança " + name}
        )
        r[name] = resource("Custom::AgentCoreRegistryRecord", props)
        if decision:
            props = dict(r["Capability0Approval"]["Properties"])
            props.update({"RecordId": att(name, "Id"), "Decision": decision})
            r[name + "Approval"] = resource("Custom::AgentCoreRegistryApproval", props)
    output(t, "RegistryId", att("Catalog", "Id"))
    output(t, "RegistryArn", att("Catalog", "Arn"))
    return t


def runtime():
    t = template(
        "Santander - Runtime MCP Fraude na conta B",
        {
            "ArtifactBucket": param(),
            "RuntimeKey": param(),
            "RuntimeName": param("santander_fraude"),
            "DiscoveryUrl": param(),
            "RuntimeAudience": param(),
            "GatewayClientId": param(),
            "GatewayArn": param(),
        },
    )
    r = t["Resources"]
    r["RuntimeRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            statement(
                ["s3:GetObject"], sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/${RuntimeKey}")
            ),
            statement(
                [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:DescribeLogStreams",
                    "logs:PutLogEvents",
                ],
                sub(
                    "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ),
            ),
        ],
    )
    r["FraudRuntime"] = resource(
        "AWS::BedrockAgentCore::Runtime",
        {
            "AgentRuntimeName": ref("RuntimeName"),
            "RoleArn": att("RuntimeRole", "Arn"),
            "AgentRuntimeArtifact": {
                "CodeConfiguration": {
                    "Runtime": "PYTHON_3_12",
                    "EntryPoint": ["python", "runtime_main.py"],
                    "Code": {"S3": {"Bucket": ref("ArtifactBucket"), "Prefix": ref("RuntimeKey")}},
                }
            },
            "ProtocolConfiguration": "MCP",
            "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
            "EnvironmentVariables": {"WORKSHOP_SERVICE": "fraud"},
            "AuthorizerConfiguration": {
                "CustomJWTAuthorizer": {
                    "DiscoveryUrl": ref("DiscoveryUrl"),
                    "AllowedAudience": [ref("RuntimeAudience")],
                    "AllowedClients": [ref("GatewayClientId")],
                    "AllowedWorkloadConfiguration": {
                        "HostingEnvironments": [{"Arn": ref("GatewayArn")}]
                    },
                }
            },
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 300, "MaxLifetime": 3600},
        },
    )
    output(t, "RuntimeArn", att("FraudRuntime", "AgentRuntimeArn"))
    output(t, "RuntimeId", att("FraudRuntime", "AgentRuntimeId"))
    return t


def origin():
    t = template(
        "Santander - supervisor na conta A; habilitar Runtime após configurar o hub",
        {
            "Project": param("santander-demo"),
            "HubAccount": param(AllowedPattern="[0-9]{12}"),
            "ArtifactBucket": param(),
            "RuntimeKey": param("workshop/not-built.zip"),
            "DiscoveryUrl": param(),
            "GatewayAudience": param(),
            "SupervisorClientId": param(""),
            "WorkshopConfig": param("{}"),
            "EnableRuntime": param("false", AllowedValues=["true", "false"]),
        },
    )
    t["Conditions"] = {"Enabled": {"Fn::Equals": [ref("EnableRuntime"), "true"]}}
    r = t["Resources"]
    r["SupervisorRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            statement(
                ["sts:AssumeRole"],
                sub("arn:${AWS::Partition}:iam::${HubAccount}:role/${Project}-registry-consumer"),
            ),
            statement(
                [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:DescribeLogStreams",
                    "logs:PutLogEvents",
                ],
                sub(
                    "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ),
            ),
            {
                "Fn::If": [
                    "Enabled",
                    statement(
                        ["s3:GetObject"],
                        sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/${RuntimeKey}"),
                    ),
                    ref("AWS::NoValue"),
                ]
            },
        ],
        name=sub("${Project}-supervisor"),
    )
    r["SupervisorRuntime"] = resource(
        "AWS::BedrockAgentCore::Runtime",
        {
            "AgentRuntimeName": "santander_supervisor",
            "RoleArn": att("SupervisorRole", "Arn"),
            "AgentRuntimeArtifact": {
                "CodeConfiguration": {
                    "Runtime": "PYTHON_3_12",
                    "EntryPoint": ["python", "runtime_main.py"],
                    "Code": {"S3": {"Bucket": ref("ArtifactBucket"), "Prefix": ref("RuntimeKey")}},
                }
            },
            "ProtocolConfiguration": "HTTP",
            "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
            "AuthorizerConfiguration": {
                "CustomJWTAuthorizer": {
                    "DiscoveryUrl": ref("DiscoveryUrl"),
                    "AllowedAudience": [ref("GatewayAudience")],
                    "AllowedClients": [ref("SupervisorClientId")],
                }
            },
            "RequestHeaderConfiguration": {
                "RequestHeaderAllowlist": [
                    "X-Amzn-Bedrock-AgentCore-Runtime-Custom-User-Token",
                ]
            },
            "EnvironmentVariables": {
                "WORKSHOP_CONFIG": ref("WorkshopConfig"),
                "WORKSHOP_SERVICE": "supervisor",
            },
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 300, "MaxLifetime": 3600},
        },
        Condition="Enabled",
    )
    output(t, "SupervisorRoleArn", att("SupervisorRole", "Arn"))
    t["Outputs"]["SupervisorRuntimeArn"] = {
        "Value": att("SupervisorRuntime", "AgentRuntimeArn"),
        "Condition": "Enabled",
    }
    return t


def policy_draft():
    t = template(
        "Santander - geração assistida de rascunho Cedar, sem publicação",
        {
            "Project": param("santander-demo"),
            "ArtifactBucket": param(),
            "ProviderKey": param(),
            "PolicyEngineId": param(),
            "PolicyEngineArn": param(),
            "GatewayArn": param(),
            "RawText": param(),
        },
    )
    r = t["Resources"]
    r["DraftRole"] = role(
        "lambda.amazonaws.com",
        [
            logs_policy(),
            statement(
                [
                    "bedrock-agentcore:StartPolicyGeneration",
                    "bedrock-agentcore:GetPolicyGeneration",
                ],
                [ref("PolicyEngineArn"), sub("${PolicyEngineArn}/policy-generation/*")],
            ),
            statement(
                [
                    "bedrock-agentcore:GetGateway",
                    "bedrock-agentcore:ListGatewayTargets",
                    "bedrock-agentcore:GetGatewayTarget",
                ],
                [ref("GatewayArn"), sub("${GatewayArn}/target/*")],
            ),
        ],
    )
    r["DraftLog"] = resource(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/lambda/${Project}-draft-provider"),
            "RetentionInDays": 7,
        },
    )
    r["DraftProvider"] = resource(
        "AWS::Lambda::Function",
        {
            "FunctionName": sub("${Project}-draft-provider"),
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "Handler": "policy_draft_handler.handler",
            "Role": att("DraftRole", "Arn"),
            "Timeout": 600,
            "MemorySize": 256,
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ProviderKey")},
        },
        DependsOn="DraftLog",
    )
    r["Draft"] = resource(
        "Custom::AgentCorePolicyDraft",
        {
            "ServiceToken": att("DraftProvider", "Arn"),
            "ServiceTimeout": 650,
            "PolicyEngineId": ref("PolicyEngineId"),
            "GatewayArn": ref("GatewayArn"),
            "RawText": ref("RawText"),
        },
        DeletionPolicy="Retain",
        UpdateReplacePolicy="Retain",
    )
    output(t, "PolicyGenerationId", att("Draft", "Id"))
    return t


def main():
    out = ROOT / "templates"
    out.mkdir(exist_ok=True)
    for name, build in [
        ("bootstrap", bootstrap),
        ("hub", hub),
        ("registry", catalog),
        ("fraud-runtime", runtime),
        ("origin", origin),
        ("policy-draft", policy_draft),
    ]:
        (out / f"{name}.json").write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n")
        examples = ROOT.parent / "config/parameters"
        examples.mkdir(parents=True, exist_ok=True)
        parameters = {
            k: (
                "set-by-pipeline"
                if k in {"LambdaKey", "ProviderKey"}
                else v.get("Default", "REPLACE_" + k.upper())
            )
            for k, v in build()["Parameters"].items()
        }
        (examples / f"{name}.example.json").write_text(
            json.dumps(parameters, indent=2, ensure_ascii=False) + "\n"
        )
    policies = ROOT.parent / "policies"
    policies.mkdir(exist_ok=True)
    (policies / "santander.local.cedar").write_text(
        "\n\n".join(statements(PolicyContract()).values()) + "\n"
    )
    (policies / "santander.aws.cedar").write_text(
        "\n\n".join(
            r["Properties"]["Definition"]["Cedar"]["Statement"]["Fn::Sub"]
            for r in hub()["Resources"].values()
            if r["Type"] == "AWS::BedrockAgentCore::Policy"
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
