"""Retrieval e geração RAG executados no Runtime; ACL nativa permanece na KB."""

import json
import os

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from botocore.exceptions import ClientError

from santander_demo.rag.client import ask, coverage_probe, verify_token

app = BedrockAgentCoreApp()


@app.entrypoint
async def run(payload, context):
    headers = {k.lower(): v for k, v in (context.request_headers or {}).items()}
    bearer = headers.get("authorization", "")
    if not bearer.startswith("Bearer "):
        raise ValueError("USER_BEARER_REQUIRED")
    token = bearer[7:]
    config = json.loads(os.environ["WORKSHOP_RAG_CONFIG"])
    environment = json.loads(os.environ["WORKSHOP_RAG_ENVIRONMENT"])
    verify_token(token, config, destination="gateway")
    aws = boto3.Session(region_name=config["region"])
    if payload.get("operation") == "probe_direct_retrieval":
        try:
            aws.client("bedrock-agent-runtime").retrieve(
                knowledgeBaseId=environment["KnowledgeBaseId"],
                retrievalQuery={"text": "políticas"},
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "AccessDeniedException":
                raise
            return {"execution": "AWS_AGENTCORE_RUNTIME", "direct_retrieval": "IAM_DENY"}
        raise AssertionError("DIRECT_RETRIEVAL_BYPASS")
    if payload.get("operation", "ask") not in {"ask", "coverage"}:
        raise ValueError("UNKNOWN_RAG_OPERATION")
    wat = aws.client("bedrock-agentcore").get_workload_access_token_for_jwt(
        workloadName=environment["WorkloadName"], userToken=token,
    )["workloadAccessToken"]
    if not wat:
        raise ValueError("WORKLOAD_IDENTITY_NOT_ESTABLISHED")
    if payload.get("operation") == "coverage":
        return {
            **await coverage_probe(config, environment, token),
            "execution": "AWS_AGENTCORE_RUNTIME",
            "user_bound_workload_token_issued": True,
        }
    result = await ask(
        config, environment, token, payload["question"], aws.client("bedrock-runtime"),
    )
    return {
        **result, "execution": "AWS_AGENTCORE_RUNTIME", "workload_identity": "VERIFIED",
        "user_bound_workload_token_issued": True,
    }
