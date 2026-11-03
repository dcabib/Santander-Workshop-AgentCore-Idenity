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
            reasons = "; ".join(result.get("statusReasons", []))[:600]
            raise RuntimeError("POLICY_GENERATION_FAILED: " + reasons)
        sleep(2)
    raise TimeoutError("POLICY_GENERATION_TIMEOUT")


def handler(event, context):
    physical = event.get("PhysicalResourceId", "failed-" + stable_token(event)[:12])
    status, data, reason = "SUCCESS", {}, "Rascunho exige revisão"
    try:
        physical, data = generate(boto3.client("bedrock-agentcore-control"), event)
    except Exception as exc:
        status = "FAILED"
        # Mensagens geradas acima contêm apenas o estado/motivo do serviço.
        # Para erros SDK, registramos código e request ID, sem payload.
        if isinstance(exc, (RuntimeError, TimeoutError)):
            reason = str(exc)[:700]
        else:
            error = getattr(exc, "response", {})
            reason = "{}: {} ({})".format(
                type(exc).__name__, error.get("Error", {}).get("Code", "PROVIDER_ERROR"),
                error.get("ResponseMetadata", {}).get("RequestId", "no-request-id"),
            )
        print(json.dumps({"error_type": type(exc).__name__, "reason": reason}))
    body = json.dumps(
        {
            "Status": status,
            "Reason": reason,
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
