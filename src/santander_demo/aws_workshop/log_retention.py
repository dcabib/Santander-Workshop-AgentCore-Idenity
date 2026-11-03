"""CloudFormation controla a retenção do log group criado pelo serviço Runtime."""

import json
import re
import time
from urllib.request import Request, urlopen

import boto3


def provision(event, logs, *, sleep=time.sleep):
    group = event["ResourceProperties"]["LogGroup"]
    if not re.fullmatch(
        r"/aws/bedrock-agentcore/runtimes/[A-Za-z][A-Za-z0-9_]*-[A-Za-z0-9]+-DEFAULT", group,
    ):
        raise ValueError("WORKSHOP_RUNTIME_LOG_GROUP_REQUIRED")
    if event["RequestType"] == "Delete":
        return {"LogGroup": group}  # Preserva evidências; a retenção continua em vigor.
    for _ in range(30):
        response = logs.describe_log_groups(logGroupNamePrefix=group, limit=5)
        if any(item["logGroupName"] == group for item in response.get("logGroups", [])):
            logs.put_retention_policy(logGroupName=group, retentionInDays=7)
            return {"LogGroup": group}
        sleep(2)
    raise TimeoutError("RUNTIME_MANAGED_LOG_GROUP_NOT_READY")


def handler(event, context):
    response = {
        "StackId": event["StackId"], "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "PhysicalResourceId": event.get("PhysicalResourceId", event["LogicalResourceId"]),
        "Status": "SUCCESS", "Data": {},
    }
    try:
        response["Data"] = provision(event, boto3.client("logs"))
    except Exception as exc:
        response.update(Status="FAILED", Reason="Log retention failed: " + type(exc).__name__)
    body = json.dumps(response).encode()
    with urlopen(Request(
        event["ResponseURL"], data=body, method="PUT", headers={"Content-Type": ""},
    ), timeout=30) as remote:
        remote.read()
