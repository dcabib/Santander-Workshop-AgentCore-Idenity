"""CloudFormation da jornada AWS: Cognito, Gateway, Runtime, Policy e Memory."""

import copy
import json
import os
import tempfile
from pathlib import Path

from infra.banking.generate import artifact_params, artifact_read, runtime_logs
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
from infra.generate import policy_draft as base_draft
from infra.rag.cognito import identity as base_identity
from santander_demo.aws_workshop.contracts import RISK, TOOLS, USER_TOKEN_HEADER, policies
from santander_demo.aws_workshop.seed import GRANTS

ROOT = Path(__file__).resolve().parent


def auth():
    return {
        "DiscoveryUrl": sub("${Issuer}/.well-known/openid-configuration"),
        "AllowedAudience": [ref("SupervisorClientId"), ref("RiscosClientId")],
        "CustomClaims": [{
            "InboundTokenClaimName": "token_use", "InboundTokenClaimValueType": "STRING",
            "AuthorizingClaimMatchValue": {
                "ClaimMatchOperator": "EQUALS", "ClaimMatchValue": {"MatchValueString": "id"},
            },
        }],
    }


def auth_params():
    return {name: param() for name in ["Issuer", "SupervisorClientId", "RiscosClientId"]}


def identity():
    t = base_identity()
    t["Description"] = "Workshop AWS - Cognito test users and confidential application clients"
    r = t["Resources"]
    base = r.pop("Client")
    t["Outputs"].pop("LoginClientId")
    for name in ["Supervisor", "Riscos"]:
        r[name + "Client"] = copy.deepcopy(base)
        r[name + "Client"]["Properties"].update(ClientName=name.lower(), GenerateSecret=True)
        r[name + "Secret"] = resource("AWS::SecretsManager::Secret", {
            "Description": "Cognito confidential workshop application: " + name,
            "SecretString": {"Fn::Join": ["", [
                '{"client_id":"', ref(name + "Client"), '","client_secret":"',
                att(name + "Client", "ClientSecret"), '"}',
            ]]},
        })
        output(t, name + "ClientId", ref(name + "Client"))
        output(t, name + "SecretArn", ref(name + "Secret"))
    output(t, "Issuer", sub("https://cognito-idp.${AWS::Region}.amazonaws.com/${Pool}"))
    return t


def log(resources, name):
    resources[name] = resource("AWS::Logs::LogGroup", {"RetentionInDays": 7})
    return statement(["logs:CreateLogStream", "logs:PutLogEvents"], sub("${" + name + ".Arn}:*"))


def gateway():
    t = template("Workshop AWS - Gateway with Cognito and enforced Cedar", {
        "Project": param(), "EngineName": param(), **artifact_params(), **auth_params(),
        "KnownGatewayArn": param(""),
    })
    t["Conditions"] = {"HasKnownGateway": {"Fn::Not": [{"Fn::Equals": [ref("KnownGatewayArn"), ""]}]}}
    r = t["Resources"]
    r["Engine"] = resource("AWS::BedrockAgentCore::PolicyEngine", {"Name": ref("EngineName")})
    r["RiskRole"] = role("lambda.amazonaws.com", [log(r, "RiskLog")])
    r["Risk"] = resource("AWS::Lambda::Function", {
        "Runtime": "python3.12", "Architectures": ["arm64"], "Timeout": 30,
        "Role": att("RiskRole", "Arn"),
        "Handler": "santander_demo.aws_workshop.backend.risk",
        "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
        "LoggingConfig": {"LogGroup": ref("RiskLog")},
    })
    r["InterceptorRole"] = role("lambda.amazonaws.com", [log(r, "InterceptorLog")])
    r["Interceptor"] = resource("AWS::Lambda::Function", {
        "Runtime": "python3.12", "Architectures": ["arm64"], "Timeout": 30,
        "Role": att("InterceptorRole", "Arn"),
        "Handler": "santander_demo.aws_workshop.interceptor.handler",
        "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
        "LoggingConfig": {"LogGroup": ref("InterceptorLog")},
        "Environment": {"Variables": {"WORKSHOP_AUTH": sub(json.dumps({
            "issuer": "${Issuer}", "clients": ["${SupervisorClientId}", "${RiscosClientId}"],
        }))}},
    })
    r["GatewayRole"] = role("bedrock-agentcore.amazonaws.com", [
        statement(["lambda:InvokeFunction"], [att("Risk", "Arn"), att("Interceptor", "Arn")]),
        statement(["bedrock-agentcore:GetPolicyEngine"], att("Engine", "PolicyEngineArn")),
        statement(["bedrock-agentcore:AuthorizeAction", "bedrock-agentcore:PartiallyAuthorizeActions"], [
            att("Engine", "PolicyEngineArn"),
            sub("arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:gateway/${Project}-*"),
        ]),
    ])
    r["GatewayRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {
        "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
        "ArnLike": {"aws:SourceArn": {"Fn::If": [
            "HasKnownGateway", ref("KnownGatewayArn"), sub(
                "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:gateway/${Project}-*"
            ),
        ]}},
    }
    r["Gateway"] = resource("AWS::BedrockAgentCore::Gateway", {
        "Name": ref("Project"), "RoleArn": att("GatewayRole", "Arn"), "ProtocolType": "MCP",
        "AuthorizerType": "CUSTOM_JWT",
        "AuthorizerConfiguration": {"CustomJWTAuthorizer": auth()},
        "PolicyEngineConfiguration": {"Arn": att("Engine", "PolicyEngineArn"), "Mode": "ENFORCE"},
        "InterceptorConfigurations": [{
            "InterceptionPoints": ["REQUEST"],
            "Interceptor": {"Lambda": {"Arn": att("Interceptor", "Arn")}},
            "InputConfiguration": {"PassRequestHeaders": True},
        }],
    })
    # CloudFormation JSONSchema usa Type/Properties; nomes das propriedades são preservados.
    properties = {
        key: {k[0].upper() + k[1:]: v for k, v in value.items()}
        for key, value in RISK["inputSchema"]["properties"].items()
    }
    r["RiskTarget"] = resource("AWS::BedrockAgentCore::GatewayTarget", {
        "Name": "riscos", "GatewayIdentifier": att("Gateway", "GatewayIdentifier"),
        "CredentialProviderConfigurations": [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}],
        "TargetConfiguration": {"Mcp": {"Lambda": {
            "LambdaArn": att("Risk", "Arn"), "ToolSchema": {"InlinePayload": [{
                "Name": RISK["name"], "Description": RISK["description"],
                "InputSchema": {
                    "Type": "object", "Properties": properties,
                    "Required": RISK["inputSchema"]["required"],
                },
            }]},
        }}},
    })
    # Logs de decisão gerenciados, para comprovar que DENY não invoca o backend.
    r["GatewayLog"] = resource("AWS::Logs::LogGroup", {
        "LogGroupName": sub("/aws/vendedlogs/${Project}/gateway"), "RetentionInDays": 7,
    })
    r["GatewayLogSource"] = resource("AWS::Logs::DeliverySource", {
        "Name": sub("${Project}-gateway"), "LogType": "APPLICATION_LOGS",
        "ResourceArn": att("Gateway", "GatewayArn"),
    })
    r["GatewayLogDestination"] = resource("AWS::Logs::DeliveryDestination", {
        "Name": sub("${Project}-gateway"), "DestinationResourceArn": att("GatewayLog", "Arn"),
        "OutputFormat": "json",
    })
    r["GatewayLogDelivery"] = resource("AWS::Logs::Delivery", {
        "DeliverySourceName": ref("GatewayLogSource"),
        "DeliveryDestinationArn": att("GatewayLogDestination", "Arn"),
    })
    for key, value in {
        "GatewayId": att("Gateway", "GatewayIdentifier"),
        "GatewayArn": att("Gateway", "GatewayArn"), "GatewayUrl": att("Gateway", "GatewayUrl"),
        "PolicyEngineId": att("Engine", "PolicyEngineId"),
        "PolicyEngineArn": att("Engine", "PolicyEngineArn"),
        "RiskLogGroup": ref("RiskLog"), "GatewayLogGroup": ref("GatewayLog"),
        "InterceptorArn": att("Interceptor", "Arn"),
        "GatewayRoleArn": att("GatewayRole", "Arn"), "GatewayRoleName": ref("GatewayRole"),
        "PropagationMode": "SIGV4_WITH_VERIFIED_USER_JWT",
    }.items():
        output(t, key, value)
    return t


def backend():
    t = template("Workshop AWS - MCP Runtime, source ACLs and native AgentCore Memory", {
        "RuntimeName": param(), "GatewayArn": param(), "GatewayRoleArn": param(),
        **artifact_params(), **auth_params(),
        **{f"User{x}Oid": param() for x in "ABCD"},
        "Grants": param(json.dumps(GRANTS)),
        "LifecycleStage": param("baseline", AllowedValues=[
            "baseline", "updated", "revoked", "deleted", "reingested",
        ]),
    })
    r = t["Resources"]
    r["Table"] = resource("AWS::DynamoDB::Table", {
        "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [{"AttributeName": x, "AttributeType": "S"} for x in ["pk", "sk"]],
        "KeySchema": [
            {"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        "SSESpecification": {"SSEEnabled": True},
        "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
    })
    r["SeedRole"] = role("lambda.amazonaws.com", [
        log(r, "SeedLog"), statement(["dynamodb:BatchWriteItem"], att("Table", "Arn")),
    ])
    r["SeedFunction"] = resource("AWS::Lambda::Function", {
        "Runtime": "python3.12", "Architectures": ["arm64"], "Timeout": 120,
        "Handler": "santander_demo.aws_workshop.seed.handler", "Role": att("SeedRole", "Arn"),
        "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
        "LoggingConfig": {"LogGroup": ref("SeedLog")},
    })
    r["Seed"] = resource("Custom::WorkshopSyntheticSource", {
        "ServiceToken": att("SeedFunction", "Arn"), "Table": ref("Table"),
        "Users": {x.lower(): ref("User" + x + "Oid") for x in "ABCD"},
        "GrantsJson": ref("Grants"),
        "LifecycleStage": ref("LifecycleStage"),
    })
    r["Memory"] = resource("AWS::BedrockAgentCore::Memory", {
        "Name": sub("${RuntimeName}_memory"), "EventExpiryDuration": 7,
        "Description": "References only; issuer/sub isolation and fresh source ACL validation",
    })
    r["RuntimeRole"] = role("bedrock-agentcore.amazonaws.com", [
        artifact_read(), runtime_logs(),
        statement(["dynamodb:GetItem"], att("Table", "Arn")),
        statement(["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents"],
                  att("Memory", "MemoryArn")),
    ])
    r["Runtime"] = resource("AWS::BedrockAgentCore::Runtime", {
        "AgentRuntimeName": ref("RuntimeName"), "RoleArn": att("RuntimeRole", "Arn"),
        "AgentRuntimeArtifact": {"CodeConfiguration": {
            "Runtime": "PYTHON_3_12", "EntryPoint": ["workshop_runtime_main.py"],
            "Code": {"S3": {"Bucket": ref("ArtifactBucket"), "Prefix": ref("ArtifactKey")}},
        }},
        "ProtocolConfiguration": "MCP", "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
        "RequestHeaderConfiguration": {"RequestHeaderAllowlist": [USER_TOKEN_HEADER]},
        "EnvironmentVariables": {"WORKSHOP_BACKEND": sub(json.dumps({
            "issuer": "${Issuer}", "clients": ["${SupervisorClientId}", "${RiscosClientId}"],
            "table": "${Table}", "memory_id": "${Memory.MemoryId}",
        }))},
        "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 900},
    }, DependsOn=["Seed"])
    r["BoundaryRole"] = role("lambda.amazonaws.com", [
        log(r, "BoundaryLog"),
        statement(
            ["bedrock-agentcore:PutResourcePolicy", "bedrock-agentcore:GetResourcePolicy"],
            att("Runtime", "AgentRuntimeArn"),
        ),
    ])
    r["BoundaryProvider"] = resource("AWS::Lambda::Function", {
        "Runtime": "python3.12", "Architectures": ["arm64"], "Timeout": 120,
        "Handler": "santander_demo.aws_workshop.runtime_boundary.handler",
        "Role": att("BoundaryRole", "Arn"),
        "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
        "LoggingConfig": {"LogGroup": ref("BoundaryLog")},
    })
    r["RuntimeBoundary"] = resource("Custom::WorkshopRuntimeBoundary", {
        "ServiceToken": att("BoundaryProvider", "Arn"),
        "RuntimeArn": att("Runtime", "AgentRuntimeArn"), "GatewayRoleArn": ref("GatewayRoleArn"),
    })
    runtime_log = sub("/aws/bedrock-agentcore/runtimes/${Runtime.AgentRuntimeId}-DEFAULT")
    r["RetentionRole"] = role("lambda.amazonaws.com", [
        log(r, "RetentionLog"),
        statement(["logs:DescribeLogGroups"], "*",
                  Condition={"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}}),
        statement(["logs:PutRetentionPolicy"], sub(
            "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:"
            "log-group:/aws/bedrock-agentcore/runtimes/${Runtime.AgentRuntimeId}-DEFAULT:*"
        )),
    ])
    r["RetentionFunction"] = resource("AWS::Lambda::Function", {
        "Runtime": "python3.12", "Architectures": ["arm64"], "Timeout": 120,
        "Role": att("RetentionRole", "Arn"), "Handler": "santander_demo.aws_workshop.log_retention.handler",
        "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
        "LoggingConfig": {"LogGroup": ref("RetentionLog")},
    })
    r["RuntimeLogRetention"] = resource("Custom::RuntimeLogRetention", {
        "ServiceToken": att("RetentionFunction", "Arn"), "LogGroup": runtime_log,
    })
    output(t, "RuntimeArn", att("Runtime", "AgentRuntimeArn"))
    output(t, "RuntimeId", att("Runtime", "AgentRuntimeId"))
    output(t, "RuntimeLogGroup", runtime_log)
    output(t, "TableName", ref("Table"))
    output(t, "MemoryId", att("Memory", "MemoryId"))
    output(t, "MemoryArn", att("Memory", "MemoryArn"))
    output(t, "SourceKind", "AWS_SIMULATED_DATABRICKS")
    output(t, "LifecycleStage", ref("LifecycleStage"))
    output(t, "RuntimeBoundary", att("RuntimeBoundary", "Boundary"))
    output(t, "GatewayIngressArn", ref("GatewayArn"))
    # ARN completo deve ser percent-encoded no path da API.
    output(t, "RuntimeUrl", {"Fn::Join": ["", [
        sub("https://bedrock-agentcore.${AWS::Region}.amazonaws.com/runtimes/"),
        sub("arn%3A${AWS::Partition}%3Abedrock-agentcore%3A${AWS::Region}%3A${AWS::AccountId}%3Aruntime%2F${Runtime.AgentRuntimeId}"),
        "/invocations?qualifier=DEFAULT",
    ]]})
    return t


def bindings():
    t = template("Workshop AWS - MCP JWT propagation and explicit per-person Cedar", {
        **auth_params(), "GatewayId": param(), "GatewayArn": param(),
        "PolicyEngineId": param(), "RuntimeUrl": param(), "RuntimeArn": param(),
        "GatewayRoleName": param(),
        **{f"User{x}Oid": param() for x in "ABC"},
    })
    t["Resources"]["GatewayRuntimeAccess"] = resource("AWS::IAM::Policy", {
        "PolicyName": "WorkshopMcpRuntimeInvocation", "Roles": [ref("GatewayRoleName")],
        "PolicyDocument": {"Version": "2012-10-17", "Statement": [
            statement(["bedrock-agentcore:InvokeAgentRuntime"], [
                ref("RuntimeArn"), sub("${RuntimeArn}/runtime-endpoint/*"),
            ]),
        ]},
    })
    t["Resources"]["Target"] = resource("AWS::BedrockAgentCore::GatewayTarget", {
        "Name": "especialista", "GatewayIdentifier": ref("GatewayId"),
        "CredentialProviderConfigurations": [{
            "CredentialProviderType": "GATEWAY_IAM_ROLE",
            "CredentialProvider": {"IamCredentialProvider": {
                "Service": "bedrock-agentcore", "Region": ref("AWS::Region"),
            }},
        }],
        "MetadataConfiguration": {"AllowedRequestHeaders": [USER_TOKEN_HEADER]},
        "TargetConfiguration": {"Mcp": {"McpServer": {
            "Endpoint": ref("RuntimeUrl"),
            "McpToolSchema": {"InlinePayload": json.dumps({"tools": TOOLS})},
        }}},
    }, DependsOn=["GatewayRuntimeAccess"])
    for name, cedar in policies(
        "${GatewayArn}", "${Issuer}", "${SupervisorClientId}", "${RiscosClientId}",
        {x.lower(): "${User" + x + "Oid}" for x in "ABCD"},
    ).items():
        t["Resources"][name] = resource("AWS::BedrockAgentCore::Policy", {
            "Name": name, "PolicyEngineId": ref("PolicyEngineId"),
            "Definition": {"Cedar": {"Statement": sub(cedar)}},
            "ValidationMode": "FAIL_ON_ANY_FINDINGS", "EnforcementMode": "ACTIVE",
        }, DependsOn=["Target"])
    output(t, "TargetId", att("Target", "TargetId"))
    return t


def agent():
    t = template("Workshop AWS - Bedrock inference and Gateway orchestration inside Runtime", {
        **artifact_params(), **auth_params(),
        "RuntimeName": param(), "GatewayUrl": param(), "ModelId": param("amazon.nova-lite-v1:0"),
    })
    r = t["Resources"]
    r["Workload"] = resource("AWS::BedrockAgentCore::WorkloadIdentity", {
        "Name": sub("${RuntimeName}_workload"),
    })
    r["RuntimeRole"] = role("bedrock-agentcore.amazonaws.com", [
        artifact_read(), runtime_logs(),
        statement(["bedrock:InvokeModel"], sub("arn:${AWS::Partition}:bedrock:${AWS::Region}::foundation-model/${ModelId}")),
        statement(["bedrock-agentcore:GetWorkloadAccessTokenForJWT"], [
            att("Workload", "WorkloadIdentityArn"),
            sub("arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/default"),
        ]),
    ])
    r["Runtime"] = resource("AWS::BedrockAgentCore::Runtime", {
        "AgentRuntimeName": ref("RuntimeName"), "RoleArn": att("RuntimeRole", "Arn"),
        "AgentRuntimeArtifact": {"CodeConfiguration": {
            "Runtime": "PYTHON_3_12", "EntryPoint": ["workshop_agent_main.py"],
            "Code": {"S3": {"Bucket": ref("ArtifactBucket"), "Prefix": ref("ArtifactKey")}},
        }},
        "ProtocolConfiguration": "HTTP", "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
        "AuthorizerConfiguration": {"CustomJWTAuthorizer": auth()},
        "RequestHeaderConfiguration": {"RequestHeaderAllowlist": ["Authorization"]},
        "EnvironmentVariables": {"WORKSHOP_AGENT": sub(json.dumps({
            "issuer": "${Issuer}", "clients": ["${SupervisorClientId}", "${RiscosClientId}"],
            "region": "${AWS::Region}", "model_id": "${ModelId}",
            "workload_name": "${RuntimeName}_workload",
            "gateways": {name: "${GatewayUrl}" for name in [
                "platform", "retail-banking", "transaction-banking", "lending-wealth",
            ]},
            "tool_prefixes": {
                "platform": "", "retail-banking": "retail___",
                "transaction-banking": "transaction___", "lending-wealth": "lending___",
            },
        }))},
        "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 900},
    })
    output(t, "RuntimeArn", att("Runtime", "AgentRuntimeArn"))
    output(t, "RuntimeId", att("Runtime", "AgentRuntimeId"))
    output(t, "WorkloadName", sub("${RuntimeName}_workload"))
    output(t, "WorkloadArn", att("Workload", "WorkloadIdentityArn"))
    return t


def policy_draft():
    t = base_draft()
    t["Parameters"]["ArtifactKey"] = t["Parameters"].pop("ProviderKey")
    t["Resources"]["DraftProvider"]["Properties"]["Code"]["S3Key"] = ref("ArtifactKey")
    # A geração valida as ações contra o schema do Gateway. A AWS autoriza
    # essa consulta como InvokeGateway, mesmo sem executar uma ferramenta.
    t["Resources"]["DraftRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"].append(
        statement(["bedrock-agentcore:InvokeGateway"], ref("GatewayArn"))
    )
    return t


def rag_agent():
    t = agent()
    t["Description"] = "Workshop AWS - RAG inference in Runtime with native managed KB ACLs"
    p = t["Parameters"]
    p["LoginClientId"] = p.pop("SupervisorClientId")
    del p["RiscosClientId"]
    del p["ModelId"]
    p.update(ModelArn=param(), RagConfig=param(), SourceBucket=param(), KnowledgeBaseId=param())
    r = t["Resources"]
    statements = r["RuntimeRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    for item in statements:
        if "bedrock:InvokeModel" in item["Action"]:
            item["Resource"] = ref("ModelArn")
    statements.append({
        "Effect": "Deny", "Action": [
            "bedrock:Retrieve", "bedrock:RetrieveAndGenerate", "bedrock:AgenticRetrieveStream",
        ], "Resource": "*",
    })
    runtime = r["Runtime"]["Properties"]
    runtime["AgentRuntimeArtifact"]["CodeConfiguration"]["EntryPoint"] = ["workshop_rag_main.py"]
    runtime["AuthorizerConfiguration"]["CustomJWTAuthorizer"]["AllowedAudience"] = [ref("LoginClientId")]
    runtime["EnvironmentVariables"] = {
        "WORKSHOP_RAG_CONFIG": ref("RagConfig"),
        "WORKSHOP_RAG_ENVIRONMENT": sub(json.dumps({
            "GatewayUrl": "${GatewayUrl}", "SourceBucket": "${SourceBucket}",
            "KnowledgeBaseId": "${KnowledgeBaseId}", "WorkloadName": "${RuntimeName}_workload",
        })),
    }
    return t


def runner():
    t = template("Workshop AWS - CodeBuild notebook execution with private source and evidence", {
        "Project": param(), "ArtifactBucket": param(), "SourceKey": param(),
        "SecretArns": {"Type": "CommaDelimitedList"},
        "ControlArns": {"Type": "CommaDelimitedList"},
        "KnowledgeArns": {"Type": "CommaDelimitedList"},
        "SourceArns": {"Type": "CommaDelimitedList"},
        "LogArns": {"Type": "CommaDelimitedList"},
        "ObserverArns": {"Type": "CommaDelimitedList"},
        "PersonaArns": {"Type": "CommaDelimitedList"},
        "TerraformPoolArn": param(), "GatewayRoleArn": param(),
        "Labs": param("", AllowedPattern=r"[0-9 ]*"),
    })
    r = t["Resources"]
    r["Role"] = role("codebuild.amazonaws.com", [
        log(r, "Log"),
        statement(["s3:GetObject", "s3:GetObjectVersion"], sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/source/*")),
        statement(["s3:PutObject"], sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}/evidence/*")),
        statement(["s3:GetBucketLocation", "s3:GetBucketAcl"], sub("arn:${AWS::Partition}:s3:::${ArtifactBucket}")),
        statement(["cloudformation:DescribeStacks"], [
            sub("arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/${Project}-*/*"),
            sub("arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/santander-rag-rag-*/*"),
            sub("arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/registry-personas-*/*"),
        ]),
        statement(["secretsmanager:GetSecretValue"], ref("SecretArns")),
        statement(["sts:AssumeRole"], {"Fn::Split": [",", {"Fn::Join": [",", [
            {"Fn::Join": [",", ref("ObserverArns")]}, {"Fn::Join": [",", ref("PersonaArns")]},
        ]]}]}),
        statement([
            "bedrock-agentcore:GetGateway", "bedrock-agentcore:GetGatewayTarget",
            "bedrock-agentcore:ListGatewayTargets", "bedrock-agentcore:GetAgentRuntime",
            "bedrock-agentcore:GetMemory", "bedrock-agentcore:GetWorkloadIdentity",
            "bedrock-agentcore:GetResourcePolicy",
            "bedrock-agentcore:GetPolicyGeneration", "bedrock-agentcore:GetPolicy",
            "bedrock-agentcore:ListPolicyGenerationAssets",
            "bedrock-agentcore:ListPolicies", "bedrock-agentcore:GetPolicyEngine",
            "bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetResourceOauth2Token",
            "bedrock-agentcore:InvokeAgentRuntime",
        ], ref("ControlArns")),
        statement([
            "bedrock-agentcore:GetWorkloadIdentity", "bedrock-agentcore:GetWorkloadAccessToken",
        ], sub(
            "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:"
            "workload-identity-directory/default"
        )),
        statement(["cognito-idp:DescribeUserPoolClient"], ref("TerraformPoolArn")),
        statement(["iam:SimulatePrincipalPolicy"], ref("PersonaArns")),
        statement(["iam:GetRole"], ref("GatewayRoleArn")),
        statement(["logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogStreams"], ref("LogArns")),
        statement(["bedrock:GetKnowledgeBase", "bedrock:GetDataSource", "bedrock:GetIngestionJob"], ref("KnowledgeArns")),
        statement(["s3:GetObject"], ref("SourceArns")),
    ])
    r["Role"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {
        "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
        "ArnLike": {"aws:SourceArn": sub(
            "arn:${AWS::Partition}:codebuild:${AWS::Region}:${AWS::AccountId}:project/${Project}-notebooks"
        )},
    }
    buildspec = {
        "version": 0.2,
        "phases": {
            "install": {
                "runtime-versions": {"python": "3.12"},
                "commands": [
                    "python -m pip install uv==0.9.7",
                    "uv sync --frozen --extra banking",
                    "uv run python -m ipykernel install --user --name python3",
                ],
            },
            "build": {"commands": [
                'uv run python scripts/verify_notebooks.py ${WORKSHOP_LABS:+--labs $WORKSHOP_LABS}',
            ]},
        },
        "artifacts": {
            "files": ["evidence/notebooks-aws.json", "evidence/executed/*.ipynb"],
            "discard-paths": False,
        },
    }
    r["Runner"] = resource("AWS::CodeBuild::Project", {
        "Name": sub("${Project}-notebooks"), "ServiceRole": att("Role", "Arn"),
        "TimeoutInMinutes": 60, "QueuedTimeoutInMinutes": 15,
        "Source": {
            "Type": "S3", "Location": sub("${ArtifactBucket}/${SourceKey}"),
            "BuildSpec": json.dumps(buildspec),
        },
        "Artifacts": {
            "Type": "S3", "Location": ref("ArtifactBucket"),
            "Path": "evidence", "NamespaceType": "BUILD_ID",
            "Name": "notebooks.zip", "Packaging": "ZIP",
        },
        "Environment": {
            "Type": "LINUX_CONTAINER", "ComputeType": "BUILD_GENERAL1_SMALL",
            "Image": "aws/codebuild/standard:7.0", "PrivilegedMode": False,
            "EnvironmentVariables": [
                {"Name": "WORKSHOP_CONFIG", "Value": "config/aws.workshop.json"},
                {"Name": "WORKSHOP_LABS", "Value": ref("Labs")},
            ],
        },
        "LogsConfig": {"CloudWatchLogs": {"Status": "ENABLED", "GroupName": ref("Log")}},
    })
    output(t, "ProjectName", ref("Runner"))
    output(t, "RoleArn", att("Role", "Arn"))
    output(t, "LogGroup", ref("Log"))
    return t


def observer():
    t = template("Workshop AWS - cross-account observer for notebook acceptance", {
        "Project": param(), "RunnerArn": param(), "ControlArns": {"Type": "CommaDelimitedList"},
    })
    r = t["Resources"]
    r["Role"] = resource("AWS::IAM::Role", {
        "RoleName": sub("${Project}-observer"),
        "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{
            "Effect": "Allow", "Action": "sts:AssumeRole", "Principal": {"AWS": ref("RunnerArn")},
        }]},
        "Policies": [{"PolicyName": "workshop-read", "PolicyDocument": {
            "Version": "2012-10-17", "Statement": [
                statement(["cloudformation:DescribeStacks"], sub(
                    "arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/${Project}-*/*"
                )),
                statement([
                    "bedrock-agentcore:GetGateway", "bedrock-agentcore:GetGatewayTarget",
                    "bedrock-agentcore:ListGatewayTargets", "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:GetMemory", "bedrock-agentcore:GetPolicyEngine",
                    "bedrock-agentcore:GetResourcePolicy", "iam:GetRole",
                ], ref("ControlArns")),
            ],
        }}],
    })
    output(t, "RoleArn", att("Role", "Arn"))
    return t


def federation_bindings():
    t = template("Workshop AWS - platform Gateway federating three account Gateways", {
        **auth_params(), "GatewayId": param(), "GatewayArn": param(), "PolicyEngineId": param(),
        **{f"User{x}Oid": param() for x in "ABC"},
        **{name + "Url": param() for name in ["Retail", "Transaction", "Lending"]},
    })
    tools = [
        {**RISK, "name": "riscos___" + RISK["name"]},
        *[{**tool, "name": "especialista___" + tool["name"]} for tool in TOOLS],
    ]
    for domain in ["Retail", "Transaction", "Lending"]:
        prefix = domain.lower()
        t["Resources"][domain + "Target"] = resource("AWS::BedrockAgentCore::GatewayTarget", {
            "Name": prefix, "GatewayIdentifier": ref("GatewayId"),
            "TargetConfiguration": {"Mcp": {"McpServer": {
                "Endpoint": ref(domain + "Url"),
                "McpToolSchema": {"InlinePayload": json.dumps({"tools": tools})},
            }}},
        })
        for name, cedar in policies(
            "${GatewayArn}", "${Issuer}", "${SupervisorClientId}", "${RiscosClientId}",
            {x.lower(): "${User" + x + "Oid}" for x in "ABC"},
        ).items():
            cedar = cedar.replace('AgentCore::Action::"', f'AgentCore::Action::"{prefix}___')
            t["Resources"][domain + name] = resource("AWS::BedrockAgentCore::Policy", {
                "Name": domain + name, "PolicyEngineId": ref("PolicyEngineId"),
                "Definition": {"Cedar": {"Statement": sub(cedar)}},
                "ValidationMode": "FAIL_ON_ANY_FINDINGS", "EnforcementMode": "ACTIVE",
            }, DependsOn=[domain + "Target"])
    return t


def origin_agent(application):
    t = agent()
    t["Description"] = "Workshop AWS - origin account " + application + " agent through platform Gateway"
    p = t["Resources"]["Runtime"]["Properties"]
    client = ref("RiscosClientId" if application == "riscos" else "SupervisorClientId")
    p["AuthorizerConfiguration"]["CustomJWTAuthorizer"]["AllowedAudience"] = [client]
    config = json.loads(p["EnvironmentVariables"]["WORKSHOP_AGENT"]["Fn::Sub"])
    config.update(
        application=application,
        gateways={name: "${GatewayUrl}" for name in [
            "platform", "retail-banking", "transaction-banking", "lending-wealth",
        ]},
        tool_prefixes={
            "platform": "", "retail-banking": "retail___",
            "transaction-banking": "transaction___", "lending-wealth": "lending___",
        },
    )
    p["EnvironmentVariables"]["WORKSHOP_AGENT"] = sub(json.dumps(config))
    return t


def generate(directory=None):
    from cedarpy import policies_to_json_str

    directory = Path(directory) if directory else ROOT / "templates"
    directory.mkdir(parents=True, exist_ok=True)
    templates = {
        "bootstrap": bootstrap(), "identity": identity(), "gateway": gateway(),
        "backend": backend(), "bindings": bindings(), "agent": agent(), "policy-draft": policy_draft(),
        "rag-agent": rag_agent(),
        "runner": runner(), "observer": observer(),
        "federation-bindings": federation_bindings(),
        "agent-riscos": origin_agent("riscos"), "agent-fraude": origin_agent("fraude"),
    }
    # cfn-lint validates CloudFormation, not Cedar. Parse every generated policy
    # before writing any template or allowing the deploy wrapper to proceed.
    for document in templates.values():
        for item in document["Resources"].values():
            if item["Type"] == "AWS::BedrockAgentCore::Policy":
                policies_to_json_str(
                    item["Properties"]["Definition"]["Cedar"]["Statement"]["Fn::Sub"]
                )
    for name, document in templates.items():
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as temporary:
            temporary.write(json.dumps(document, indent=2) + "\n")
        os.replace(temporary.name, directory / f"{name}.json")
    return templates


if __name__ == "__main__":
    generate()
