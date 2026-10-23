"""IaC do laboratório 07. Geração local, sem chamadas à AWS."""

import json
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
from santander_demo.registry_workflow.contracts import TOOL

ROOT = Path(__file__).resolve().parent


def human_role(statements, service=None):
    r = role(service or "lambda.amazonaws.com", statements)
    trust = r["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    if not service:
        trust.clear()
    trust.append(
        {"Effect": "Allow", "Principal": {"AWS": ref("OperatorArn")}, "Action": "sts:AssumeRole"}
    )
    return r


def function(resources, name, role_id, *, kinds=None, handler=None):
    resources[name] = resource(
        "AWS::Lambda::Function",
        {
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "MemorySize": 512,
            "Timeout": 600 if kinds else 30,
            "Role": att(role_id, "Arn"),
            "Code": {"S3Bucket": ref("ArtifactBucket"), "S3Key": ref("ArtifactKey")},
            "Handler": handler or "santander_demo.registry_workflow.provider.handler",
            **({"Environment": {"Variables": {"RESOURCE_KINDS": kinds}}} if kinds else {}),
        },
    )
    resources[name + "Log"] = resource(
        "AWS::Logs::LogGroup",
        {
            "LogGroupName": sub(f"/aws/lambda/${{{name}}}"),
            "RetentionInDays": 7,
        },
    )


def foundation():
    t = template(
        "Registry personas - infraestrutura, providers e permissoes separadas",
        {
            **artifact_params(),
            "OperatorArn": param(),
            "RecoveryRegistryArn": param(""),
            "Project": param("registry-personas"),
            "RuntimeName": param(
                "registry_personas_demo", AllowedPattern="[A-Za-z][A-Za-z0-9_]{0,47}"
            ),
        },
    )
    r = t["Resources"]
    logs = statement(
        ["logs:CreateLogStream", "logs:PutLogEvents"],
        sub(
            "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/*:log-stream:*"
        ),
    )
    all_registries = sub(
        "arn:${AWS::Partition}:agent-registry:${AWS::Region}:${AWS::AccountId}:registry/*"
    )
    r["RegistryAdminRole"] = role(
        "lambda.amazonaws.com",
        [
            logs,
            statement(
                [
                    "agent-registry:CreateRegistry",
                    "agent-registry:GetRegistry",
                    "agent-registry:DeleteRegistry",
                ],
                all_registries,
            ),
            statement(
                [
                    "bedrock-agentcore:CreateWorkloadIdentity",
                    "bedrock-agentcore:GetWorkloadIdentity",
                    "bedrock-agentcore:DeleteWorkloadIdentity",
                ],
                sub(
                    "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/*"
                ),
            ),
            statement(
                ["iam:CreateServiceLinkedRole"],
                sub(
                    "arn:${AWS::Partition}:iam::${AWS::AccountId}:role/aws-service-role/agent-registry.amazonaws.com/AWSServiceRoleForAgentRegistry"
                ),
                Condition={"StringEquals": {"iam:AWSServiceName": "agent-registry.amazonaws.com"}},
            ),
        ],
    )
    function(r, "RegistryProvider", "RegistryAdminRole", kinds="Registry")
    r["Registry"] = resource(
        "Custom::Registry",
        {
            "ServiceToken": att("RegistryProvider", "Arn"),
            "Kind": "Registry",
            "RecoveryArn": ref("RecoveryRegistryArn"),
        },
        DependsOn="RegistryProviderLog",
    )
    registry_arn = att("Registry", "Arn")
    records = sub("${Registry.Arn}/record/*")
    read_control = statement(
        ["agent-registry:GetRegistryRecord", "agent-registry:ListRegistryRecords"],
        [registry_arn, records],
    )
    r["PublisherRole"] = human_role(
        [
            logs,
            read_control,
            statement(
                [
                    "agent-registry:CreateRegistryRecord",
                    "agent-registry:DeleteRegistryRecord",
                    "agent-registry:SubmitRegistryRecordForApproval",
                ],
                [registry_arn, records],
            ),
        ],
        "lambda.amazonaws.com",
    )
    r["ApproverRole"] = human_role(
        [
            logs,
            read_control,
            statement(["agent-registry:UpdateRegistryRecordStatus"], records),
        ],
        "lambda.amazonaws.com",
    )
    function(r, "PublisherProvider", "PublisherRole", kinds="Record,Submission")
    function(r, "ApproverProvider", "ApproverRole", kinds="Approval")
    r["ToolRole"] = role("lambda.amazonaws.com", [logs])
    function(
        r, "RiskTool", "ToolRole", handler="santander_demo.registry_workflow.contracts.tool_handler"
    )
    r["GatewayRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [statement(["lambda:InvokeFunction"], att("RiskTool", "Arn"))],
    )
    r["Gateway"] = resource(
        "AWS::BedrockAgentCore::Gateway",
        {
            "Name": ref("Project"),
            "RoleArn": att("GatewayRole", "Arn"),
            "ProtocolType": "MCP",
            "AuthorizerType": "AWS_IAM",
        },
    )
    r["Target"] = resource(
        "AWS::BedrockAgentCore::GatewayTarget",
        {
            "Name": "risco",
            "GatewayIdentifier": att("Gateway", "GatewayIdentifier"),
            "CredentialProviderConfigurations": [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}],
            "TargetConfiguration": {
                "Mcp": {
                    "Lambda": {
                        "LambdaArn": att("RiskTool", "Arn"),
                        "ToolSchema": {
                            "InlinePayload": [
                                {
                                    "Name": TOOL["name"],
                                    "Description": TOOL["description"],
                                    "InputSchema": {
                                        "Type": "object",
                                        "Properties": {"customer_id": {"Type": "string"}},
                                        "Required": ["customer_id"],
                                    },
                                }
                            ]
                        },
                    }
                }
            },
        },
    )
    invoke_gateway = statement(["bedrock-agentcore:InvokeGateway"], att("Gateway", "GatewayArn"))
    r["RuntimeRole"] = role(
        "bedrock-agentcore.amazonaws.com", [artifact_read(), runtime_logs(), invoke_gateway]
    )
    r["Runtime"] = resource(
        "AWS::BedrockAgentCore::Runtime",
        {
            "AgentRuntimeName": ref("RuntimeName"),
            "RoleArn": att("RuntimeRole", "Arn"),
            "AgentRuntimeArtifact": {
                "CodeConfiguration": {
                    "Runtime": "PYTHON_3_12",
                    "EntryPoint": ["registry_runtime_main.py"],
                    "Code": {"S3": {"Bucket": ref("ArtifactBucket"), "Prefix": ref("ArtifactKey")}},
                }
            },
            "ProtocolConfiguration": "HTTP",
            "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
            "EnvironmentVariables": {"GATEWAY_URL": att("Gateway", "GatewayUrl")},
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 600},
        },
        DependsOn=["Target", "Registry"],
    )
    invoke_runtime = statement(
        ["bedrock-agentcore:InvokeAgentRuntime"],
        [att("Runtime", "AgentRuntimeArn"), sub("${Runtime.AgentRuntimeArn}/runtime-endpoint/*")],
    )
    r["DeveloperRole"] = human_role([invoke_runtime, invoke_gateway])
    r["ConsumerRole"] = human_role(
        [
            statement(
                [
                    "agent-registry:ListDiscoverableRegistryRecords",
                    "agent-registry:SearchDiscoverableRegistryRecords",
                ],
                registry_arn,
            ),
            statement(["agent-registry:GetDiscoverableRegistryRecord"], records),
            invoke_runtime,
        ]
    )
    for name in ("Developer", "Publisher", "Approver", "Consumer"):
        output(t, name + "RoleArn", att(name + "Role", "Arn"))
    for name in ("Publisher", "Approver"):
        output(t, name + "ProviderArn", att(name + "Provider", "Arn"))
    output(t, "RegistryId", att("Registry", "Id"))
    output(t, "RegistryArn", registry_arn)
    output(t, "GatewayUrl", att("Gateway", "GatewayUrl"))
    output(t, "GatewayArn", att("Gateway", "GatewayArn"))
    output(t, "RuntimeArn", att("Runtime", "AgentRuntimeArn"))
    return t


def publish():
    t = template(
        "Registry personas - criar rascunhos imutaveis",
        {
            "RegistryId": param(),
            "PublisherProviderArn": param(),
            "McpPackage": param(),
            "AgentPackage": param(),
        },
    )
    for name in ("Mcp", "Agent"):
        t["Resources"][name] = resource(
            "Custom::RegistryRecord",
            {
                "ServiceToken": ref("PublisherProviderArn"),
                "Kind": "Record",
                "RegistryId": ref("RegistryId"),
                "Package": ref(name + "Package"),
            },
        )
        output(t, name + "RecordId", att(name, "Id"))
        output(t, name + "Digest", att(name, "Digest"))
    return t


def transition(approve=False):
    actor = "Approver" if approve else "Publisher"
    t = template(
        "Registry personas - decisao revisada"
        if approve
        else "Registry personas - submeter para revisao",
        {
            "RegistryId": param(),
            actor + "ProviderArn": param(),
            "McpRecordId": param(),
            "AgentRecordId": param(),
            **(
                {
                    name + suffix: param(
                        **(
                            {"AllowedValues": ["APPROVED", "REJECTED"]}
                            if suffix == "Decision"
                            else {}
                        )
                    )
                    for name in ("Mcp", "Agent")
                    for suffix in ("Digest", "Decision")
                }
                if approve
                else {}
            ),
        },
    )
    for name in ("Mcp", "Agent"):
        t["Resources"][name] = resource(
            "Custom::RegistryApproval" if approve else "Custom::RegistrySubmission",
            {
                "ServiceToken": ref(actor + "ProviderArn"),
                "Kind": "Approval" if approve else "Submission",
                "RegistryId": ref("RegistryId"),
                "RecordId": ref(name + "RecordId"),
                **(
                    {"ReviewedDigest": ref(name + "Digest"), "Decision": ref(name + "Decision")}
                    if approve
                    else {}
                ),
            },
        )
    return t


def main():
    ROOT.joinpath("templates").mkdir(exist_ok=True)
    for name, value in {
        "bootstrap": bootstrap(),
        "foundation": foundation(),
        "publish": publish(),
        "submit": transition(),
        "approve": transition(True),
    }.items():
        (ROOT / "templates" / (name + ".json")).write_text(json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    main()
