"""Resource policy do Runtime gerenciada exclusivamente por CloudFormation."""

import json
import re
from urllib.request import Request, urlopen

import boto3


def policy(runtime_arn, gateway_role_arn):
    runtime = re.fullmatch(
        r"arn:aws:bedrock-agentcore:us-east-1:(\d{12}):runtime/[A-Za-z0-9_-]+",
        runtime_arn,
    )
    if not runtime or not re.fullmatch(
        rf"arn:aws:iam::{runtime[1]}:role/[\w+=,.@/-]+", gateway_role_arn,
    ):
        raise ValueError("EXACT_RUNTIME_AND_SAME_ACCOUNT_GATEWAY_ROLE_REQUIRED")
    return {"Version": "2012-10-17", "Statement": [
        {
            "Sid": "AllowGatewayInvocation", "Effect": "Allow",
            "Principal": {"AWS": gateway_role_arn},
            "Action": "bedrock-agentcore:InvokeAgentRuntime", "Resource": runtime_arn,
        },
        {
            "Sid": "DenyOtherInvokers", "Effect": "Deny", "Principal": {"AWS": "*"},
            "Action": ["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:InvokeAgentRuntimeForUser"],
            "Resource": runtime_arn,
            "Condition": {"ArnNotEquals": {"aws:PrincipalArn": gateway_role_arn}},
        },
    ]}


def provision(event, control):
    props = event["ResourceProperties"]
    document = policy(props["RuntimeArn"], props["GatewayRoleArn"])
    if event["RequestType"] == "Delete":
        # O Runtime é dono da policy. Mantê-la até excluir o Runtime evita uma
        # janela de invocação direta durante o teardown ou a substituição.
        return {"Boundary": "PRESERVED_UNTIL_RUNTIME_DELETION"}
    if event["RequestType"] not in {"Create", "Update"}:
        raise ValueError("UNSUPPORTED_CLOUDFORMATION_OPERATION")
    control.put_resource_policy(resourceArn=props["RuntimeArn"], policy=json.dumps(document))
    actual = json.loads(control.get_resource_policy(resourceArn=props["RuntimeArn"])["policy"])
    if actual != document:
        raise ValueError("RUNTIME_BOUNDARY_READBACK_MISMATCH")
    return {"Boundary": "GATEWAY_ROLE_ONLY"}


def handler(event, context):
    response = {
        "StackId": event["StackId"], "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "PhysicalResourceId": event.get("PhysicalResourceId", event["ResourceProperties"]["RuntimeArn"]),
        "Status": "SUCCESS", "Data": {},
    }
    try:
        response["Data"] = provision(event, boto3.client("bedrock-agentcore-control"))
    except Exception as exc:
        response.update(Status="FAILED", Reason="Runtime boundary failed: " + type(exc).__name__)
    body = json.dumps(response).encode()
    with urlopen(Request(
        event["ResponseURL"], data=body, method="PUT", headers={"Content-Type": ""},
    ), timeout=30) as remote:
        remote.read()
