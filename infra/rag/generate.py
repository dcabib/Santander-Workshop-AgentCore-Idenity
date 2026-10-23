"""IaC do lab 16: Bedrock MANAGED, ACLs S3, Identity OBO e conector nativo."""

import copy
import json
from pathlib import Path

from infra.banking.generate import artifact_params
from infra.federation.generate import UUID, authorizer
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
from infra.rag import cognito
from santander_demo.rag.contract import EMAIL_PATTERN, cedar, connector_configuration

ROOT = Path(__file__).resolve().parent


def users_params():
    return {
        **{f"User{x}Oid": param(AllowedPattern=UUID) for x in "ABCD"},
        **{f"User{x}Email": param(NoEcho=True, AllowedPattern=EMAIL_PATTERN) for x in "ABCD"},
    }


def data():
    t = template(
        "Santander RAG - fully managed Knowledge Base and synthetic ACL-aware S3 corpus",
        {"Project": param(), **artifact_params(), **users_params(), "CorpusDigest": param()},
    )
    r = t["Resources"]
    base = bootstrap()
    r["SourceBucket"] = copy.deepcopy(base["Resources"]["Artifacts"])
    r["SourceBucket"]["DeletionPolicy"] = "RetainExceptOnCreate"
    r["SourceTLS"] = json.loads(
        json.dumps(base["Resources"]["TLSOnly"]).replace("Artifacts", "SourceBucket")
    )
    r["KnowledgeRole"] = role(
        "bedrock.amazonaws.com",
        [
            statement(["s3:ListBucket"], att("SourceBucket", "Arn")),
            statement(["s3:GetObject"], sub("${SourceBucket.Arn}/*")),
        ],
    )
    r["KnowledgeRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {
        "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
        "ArnLike": {
            "aws:SourceArn": sub(
                "arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:knowledge-base/*"
            )
        },
    }
    r["KnowledgeBase"] = resource(
        "AWS::Bedrock::KnowledgeBase",
        {
            "Name": ref("Project"),
            "RoleArn": att("KnowledgeRole", "Arn"),
            "KnowledgeBaseConfiguration": {
                "Type": "MANAGED",
                "ManagedKnowledgeBaseConfiguration": {"EmbeddingModelType": "MANAGED"},
            },
        },
        DeletionPolicy="RetainExceptOnCreate",
        UpdateReplacePolicy="Retain",
    )
    r["DataSource"] = resource(
        "AWS::Bedrock::DataSource",
        {
            "Name": "synthetic-acl-corpus",
            "KnowledgeBaseId": ref("KnowledgeBase"),
            "DataDeletionPolicy": "RETAIN",
            "DataSourceConfiguration": {
                "Type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
                "ManagedKnowledgeBaseConnectorConfiguration": {
                    "ConnectorParameters": {
                        "type": "S3",
                        "version": "1",
                        "aclEnabled": True,
                        "connectionConfiguration": {
                            "bucketName": ref("SourceBucket"),
                            "bucketOwnerAccountId": ref("AWS::AccountId"),
                        },
                        "filterConfiguration": {"inclusionPrefixes": ["documents/"]},
                        "aclConfiguration": {
                            "globalAccessControlListS3Uri": sub(
                                "s3://${SourceBucket}/acl/global-acl.json"
                            )
                        },
                    }
                },
            },
            "VectorIngestionConfiguration": {
                "ParsingConfiguration": {"ParsingStrategy": "SMART_PARSING"},
            },
        },
        DeletionPolicy="RetainExceptOnCreate",
        UpdateReplacePolicy="Retain",
    )
    r["CorpusLog"] = resource(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/lambda/${Project}-corpus"),
            "RetentionInDays": 7,
        },
    )
    r["CorpusRole"] = role(
        "lambda.amazonaws.com",
        [
            statement(["logs:CreateLogStream", "logs:PutLogEvents"], sub("${CorpusLog.Arn}:*")),
            statement(
                ["s3:PutObject"],
                [sub("${SourceBucket.Arn}/documents/*"), sub("${SourceBucket.Arn}/acl/*")],
            ),
            statement(
                ["bedrock:StartIngestionJob", "bedrock:GetIngestionJob", "bedrock:GetDataSource"],
                att("KnowledgeBase", "KnowledgeBaseArn"),
            ),
        ],
    )
    r["CorpusFunction"] = resource(
        "AWS::Lambda::Function",
        {
            "FunctionName": sub("${Project}-corpus"),
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "Handler": "santander_demo.rag.seed.handler",
            "Role": att("CorpusRole", "Arn"),
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
            "Timeout": 900,
            "MemorySize": 256,
            "LoggingConfig": {"LogGroup": ref("CorpusLog")},
        },
    )
    r["Corpus"] = resource(
        "Custom::ManagedKnowledgeBaseCorpus",
        {
            "ServiceToken": att("CorpusFunction", "Arn"),
            "Bucket": ref("SourceBucket"),
            "KnowledgeBaseId": ref("KnowledgeBase"),
            "DataSourceId": att("DataSource", "DataSourceId"),
            "CorpusDigest": ref("CorpusDigest"),
            "Users": {
                label.lower(): {"oid": ref(f"User{label}Oid"), "email": ref(f"User{label}Email")}
                for label in "ABCD"
            },
        },
    )
    for name, value in {
        "SourceBucket": ref("SourceBucket"),
        "KnowledgeBaseId": ref("KnowledgeBase"),
        "KnowledgeBaseArn": att("KnowledgeBase", "KnowledgeBaseArn"),
        "DataSourceId": att("DataSource", "DataSourceId"),
        "IngestionJobId": att("Corpus", "IngestionJobId"),
    }.items():
        output(t, name, value)
    return t


def access():
    t = template(
        "Santander RAG - Identity OBO, native managed KB connector and principal-bound Policy",
        {
            "Project": param(),
            "EngineName": param(AllowedPattern=r"[A-Za-z][A-Za-z0-9_]*"),
            "TenantId": param(AllowedPattern=UUID),
            "BrokerClientId": param(AllowedPattern=UUID),
            "GatewayClientId": param(AllowedPattern=UUID),
            "BrokerSecretArn": param(),
            "KnowledgeBaseId": param(),
            "KnowledgeBaseArn": param(),
            "CallerPrincipalArn": param(),
            "ModelArn": param(),
            **users_params(),
        },
    )
    # D não tem regra permit; não há parâmetros desse usuário no stack de acesso.
    del t["Parameters"]["UserDEmail"]
    del t["Parameters"]["UserDOid"]
    r = t["Resources"]
    r["GatewayRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            statement(["bedrock:GetKnowledgeBase", "bedrock:Retrieve"], ref("KnowledgeBaseArn")),
            statement(["bedrock-agentcore:GetPolicyEngine"], att("Engine", "PolicyEngineArn")),
            # CreateGateway avalia Policy antes de expor o ARN gerado. O prefixo
            # restringe a permissão ao nome deste laboratório, conta e região.
            statement(
                [
                    "bedrock-agentcore:AuthorizeAction",
                    "bedrock-agentcore:PartiallyAuthorizeActions",
                ],
                [
                    att("Engine", "PolicyEngineArn"),
                    sub(
                        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:"
                        "${AWS::AccountId}:gateway/${Project}-*"
                    ),
                ],
            ),
        ],
    )
    r["GatewayRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {
        "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
        "ArnLike": {
            "aws:SourceArn": sub(
                "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:gateway/*"
            )
        },
    }
    auth = authorizer(ref("GatewayClientId"))
    # O caller deste Gateway é o broker que fez OBO, e não o cliente público.
    auth = json.loads(json.dumps(auth).replace("CallerClientId", "BrokerClientId"))
    r["Engine"] = resource("AWS::BedrockAgentCore::PolicyEngine", {"Name": ref("EngineName")})
    r["Gateway"] = resource(
        "AWS::BedrockAgentCore::Gateway",
        {
            "Name": ref("Project"),
            "RoleArn": att("GatewayRole", "Arn"),
            "ProtocolType": "MCP",
            "AuthorizerType": "CUSTOM_JWT",
            "AuthorizerConfiguration": {"CustomJWTAuthorizer": auth},
            "PolicyEngineConfiguration": {
                "Arn": att("Engine", "PolicyEngineArn"),
                "Mode": "ENFORCE",
            },
        },
    )
    connector = connector_configuration(ref("KnowledgeBaseId"))
    r["Target"] = resource(
        "AWS::BedrockAgentCore::GatewayTarget",
        {
            "Name": "rag",
            "GatewayIdentifier": att("Gateway", "GatewayIdentifier"),
            "CredentialProviderConfigurations": [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}],
            "TargetConfiguration": {
                "Mcp": {
                    "Connector": {
                        "Source": {"ConnectorId": connector["source"]["connectorId"]},
                        "Enabled": connector["enabled"],
                        "Configurations": [
                            {
                                "Name": c["name"],
                                "ParameterValues": c["parameterValues"],
                                "ParameterOverrides": [
                                    {"Path": p["path"], "Visible": p["visible"]}
                                    for p in c["parameterOverrides"]
                                ],
                            }
                            for c in connector["configurations"]
                        ],
                    }
                }
            },
        },
    )
    users = {
        x.lower(): {"oid": "${User" + x + "Oid}", "email": "${User" + x + "Email}"} for x in "ABCD"
    }
    for name, policy in cedar(
        "${Gateway.GatewayArn}", "${TenantId}", "${BrokerClientId}", users
    ).items():
        r[name] = resource(
            "AWS::BedrockAgentCore::Policy",
            {
                "Name": name,
                "PolicyEngineId": att("Engine", "PolicyEngineId"),
                "Definition": {"Cedar": {"Statement": sub(policy)}},
                "ValidationMode": "FAIL_ON_ANY_FINDINGS",
                "EnforcementMode": "ACTIVE",
            },
            DependsOn=["Target"],
        )
    r["Workload"] = resource(
        "AWS::BedrockAgentCore::WorkloadIdentity", {"Name": sub("${Project}-broker")}
    )
    r["OAuth"] = resource(
        "AWS::BedrockAgentCore::OAuth2CredentialProvider",
        {
            "Name": sub("${Project}-obo"),
            "CredentialProviderVendor": "CustomOauth2",
            "Oauth2ProviderConfigInput": {
                "CustomOauth2ProviderConfig": {
                    "OauthDiscovery": {"DiscoveryUrl": auth["DiscoveryUrl"]},
                    "ClientId": ref("BrokerClientId"),
                    "ClientSecretSource": "EXTERNAL",
                    "ClientSecretConfig": {
                        "SecretId": ref("BrokerSecretArn"),
                        "JsonKey": "client_secret",
                    },
                    "ClientAuthenticationMethod": "CLIENT_SECRET_POST",
                    "OnBehalfOfTokenExchangeConfig": {"GrantType": "JWT_AUTHORIZATION_GRANT"},
                }
            },
        },
    )
    r["CallerRole"] = resource(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ref("CallerPrincipalArn")},
                        "Action": "sts:AssumeRole",
                    }
                ],
            },
            "Policies": [
                {
                    "PolicyName": "rag-caller",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
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
                                    att("Workload", "WorkloadIdentityArn"),
                                    att("OAuth", "CredentialProviderArn"),
                                ],
                            ),
                            statement(["bedrock:InvokeModel"], ref("ModelArn")),
                            {
                                "Effect": "Deny",
                                "Action": [
                                    "bedrock:Retrieve",
                                    "bedrock:RetrieveAndGenerate",
                                    "bedrock:AgenticRetrieveStream",
                                ],
                                "Resource": "*",
                            },
                        ],
                    },
                }
            ],
        },
    )
    r["GatewayLog"] = resource(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": sub("/aws/vendedlogs/${Project}/gateway"),
            "RetentionInDays": 7,
        },
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
    for name, value in {
        "GatewayId": att("Gateway", "GatewayIdentifier"),
        "GatewayArn": att("Gateway", "GatewayArn"),
        "GatewayUrl": att("Gateway", "GatewayUrl"),
        "TargetId": att("Target", "TargetId"),
        "PolicyEngineId": att("Engine", "PolicyEngineId"),
        "PolicyEngineArn": att("Engine", "PolicyEngineArn"),
        "OAuthProviderName": sub("${Project}-obo"),
        "OAuthProviderArn": att("OAuth", "CredentialProviderArn"),
        "WorkloadName": sub("${Project}-broker"),
        "CallerRoleArn": att("CallerRole", "Arn"),
        "GatewayLogGroup": ref("GatewayLog"),
    }.items():
        output(t, name, value)
    return t


def generate(directory=None):
    directory = Path(directory) if directory else ROOT / "templates"
    directory.mkdir(parents=True, exist_ok=True)
    docs = {
        "bootstrap": bootstrap(),
        "identity": cognito.identity(),
        "data": data(),
        "access": access(),
        "access-cognito": cognito.access(access()),
    }
    for name, doc in docs.items():
        (directory / f"{name}.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        )
    return docs


if __name__ == "__main__":
    generate()
