"""Custom resource CloudFormation: define senhas sintéticas e exporta os subjects."""

import json
from urllib.request import Request, urlopen

import boto3


def provision(event, cognito, secrets):
    if event["RequestType"] == "Delete":
        return {}  # Usuários e segredos têm seus próprios recursos CloudFormation.
    props = event["ResourceProperties"]
    result = {}
    for label in "ABCD":
        value = json.loads(
            secrets.get_secret_value(SecretId=props[f"User{label}SecretArn"])["SecretString"]
        )
        cognito.admin_set_user_password(
            UserPoolId=props["UserPoolId"],
            Username=value["username"],
            Password=value["password"],
            Permanent=True,
        )
        user = cognito.admin_get_user(UserPoolId=props["UserPoolId"], Username=value["username"])
        result[f"User{label}Oid"] = next(
            a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub"
        )
    return result


def handler(event, context):
    response = {
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
        "PhysicalResourceId": event.get("PhysicalResourceId", event["LogicalResourceId"]),
        "Status": "SUCCESS",
        "Data": {},
    }
    try:
        response["Data"] = provision(
            event, boto3.client("cognito-idp"), boto3.client("secretsmanager")
        )
    except Exception as exc:
        response.update(
            Status="FAILED", Reason=f"Identity provisioning failed: {type(exc).__name__}"
        )
    body = json.dumps(response).encode()
    request = Request(event["ResponseURL"], data=body, method="PUT", headers={"Content-Type": ""})
    with urlopen(request, timeout=30) as remote:
        remote.read()
