"""Geração assistida de rascunho via CloudFormation; nunca publica uma Policy."""

import json
import time
import urllib.request

import boto3
from registry_handler import stable_token


def generate(client, event, sleep=time.sleep, max_polls=150):
    if event["RequestType"] == "Delete":
        # A API não expõe DeletePolicyGeneration. O template retém esse histórico.
        return event["PhysicalResourceId"], {"Retained": "true"}
    p = event["ResourceProperties"]
    token = stable_token(event)
    result = client.start_policy_generation(
        policyEngineId=p["PolicyEngineId"],
        resource={"arn": p["GatewayArn"]},
        content={"rawText": p["RawText"]},
        name="san_draft_" + token[:12],
        clientToken=token,
    )
    args = {
        "policyEngineId": p["PolicyEngineId"],
        "policyGenerationId": result["policyGenerationId"],
    }
    for _ in range(max_polls):
        result = client.get_policy_generation(**args)
        if result["status"] == "GENERATED":
            return result["policyGenerationArn"], {
                "Id": result["policyGenerationId"],
                "Status": result["status"],
                "ReviewRequired": "true",
            }
        if result["status"].endswith("_FAILED"):
            raise RuntimeError("POLICY_GENERATION_FAILED")
        sleep(2)
    raise TimeoutError("POLICY_GENERATION_TIMEOUT")


def handler(event, context):
    physical = event.get("PhysicalResourceId", "failed-" + stable_token(event)[:12])
    status, data = "SUCCESS", {}
    try:
        physical, data = generate(boto3.client("bedrock-agentcore-control"), event)
    except Exception as exc:
        status = "FAILED"
        print(json.dumps({"error_type": type(exc).__name__}))
    body = json.dumps(
        {
            "Status": status,
            "Reason": "Rascunho exige revisão" if status == "SUCCESS" else "Falha na geração",
            "PhysicalResourceId": physical,
            "StackId": event["StackId"],
            "RequestId": event["RequestId"],
            "LogicalResourceId": event["LogicalResourceId"],
            "Data": data,
        }
    ).encode()
    with urllib.request.urlopen(
        urllib.request.Request(
            event["ResponseURL"],
            data=body,
            method="PUT",
            headers={"Content-Type": "", "Content-Length": str(len(body))},
        ),
        timeout=20,
    ):
        pass
