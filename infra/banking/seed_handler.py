"""Fixtures DynamoDB executadas exclusivamente como custom resource CloudFormation."""

import hashlib
import json
import urllib.request

import boto3
from botocore.exceptions import ClientError

from santander_demo.banking.spec import data_file


def seed(event, dynamodb):
    props = event["ResourceProperties"]
    fixtures = data_file("fixtures.json")[props["Lob"]]
    if set(props["Tables"]) != set(fixtures):
        raise ValueError("TABLE_SET_MISMATCH")
    if event["RequestType"] == "Delete":
        return 0  # Tables e fixtures usam Retain; nunca apagar dados durante rollback.
    if event["RequestType"] not in {"Create", "Update"}:
        raise ValueError("INVALID_REQUEST")
    count = 0
    for name, items in fixtures.items():
        table = dynamodb.Table(props["Tables"][name])
        for item in items:
            key = next(iter(item))
            try:
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(#pk)",
                    ExpressionAttributeNames={"#pk": key},
                )
                count += 1
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
    return count


def handler(event, context):
    physical = event.get("PhysicalResourceId") or (
        "banking-seed-"
        + hashlib.sha256((event["StackId"] + event["LogicalResourceId"]).encode()).hexdigest()[:24]
    )
    status, data = "SUCCESS", {}
    try:
        data["Inserted"] = seed(event, boto3.resource("dynamodb"))
    except Exception as exc:
        status = "FAILED"
        print(json.dumps({"event": "seed_failed", "type": type(exc).__name__}))
    body = json.dumps(
        {
            "Status": status,
            "Reason": "Fixtures sintéticas: consulte o status do recurso",
            "PhysicalResourceId": physical,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "Data": data,
        }
    ).encode()
    request = urllib.request.Request(
        event["ResponseURL"],
        method="PUT",
        data=body,
        headers={"Content-Type": "", "Content-Length": str(len(body))},
    )
    with urllib.request.urlopen(request, timeout=20):
        pass
