"""Verificação real da demo, sem APIs de provisionamento e sem exportar tokens."""

import json
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit
from uuid import uuid4

import boto3
import httpx
from botocore.config import Config

from santander_demo.terraform_lab.backend import TOOL_NAME, customer_profile
from santander_demo.terraform_lab.runtime import (
    connect_gateway,
    gateway_access_token,
    list_tools,
    validate_gateway,
)


def runtime_url(config):
    return (
        f"https://bedrock-agentcore.{config['region']}.amazonaws.com/runtimes/"
        f"{quote(config['runtime_arn'], safe='')}/invocations?qualifier=DEFAULT"
    )


def invoke_runtime(config, session, *, customer_id="C001", mode="deterministic"):
    client = session.client(
        "bedrock-agentcore",
        config=Config(read_timeout=180, connect_timeout=15, retries={"max_attempts": 0}),
    )
    response = client.invoke_agent_runtime(
        agentRuntimeArn=config["runtime_arn"],
        qualifier="DEFAULT",
        runtimeSessionId=str(uuid4()),
        payload=json.dumps({"customer_id": customer_id, "mode": mode}).encode(),
        contentType="application/json",
    )
    body = response["response"].read()
    result = json.loads(body)
    if (
        result.get("mode") != "AWS_LIVE"
        or result.get("execution") != mode
        or result.get("identity_flow") != "M2M"
        or result.get("workload_name") != config["workload_name"]
        or result.get("provider_name") != config["provider_name"]
        or not result.get("records")
        or not result.get("tool_calls")
        or set(result["tool_calls"]) != {TOOL_NAME}
    ):
        raise RuntimeError("RUNTIME_RESULT_CONTRACT_MISMATCH")
    expected = customer_profile(customer_id)
    for record in result["records"]:
        if any(record.get(k) != v for k, v in expected.items()):
            raise RuntimeError("SYNTHETIC_DATA_MISMATCH")
        proof = record.get("execution", {})
        if not proof.get("lambda_request_id") or not proof.get("gateway_request_id"):
            raise RuntimeError("BACKEND_EXECUTION_EVIDENCE_MISSING")
    if mode == "llm" and not result.get("answer", "").strip():
        raise RuntimeError("MODEL_ANSWER_MISSING")
    return {
        "status": "PASS",
        "runtime_request_id": response["ResponseMetadata"]["RequestId"],
        "result": result,
    }


def require_denial(response):
    # Exige resposta atribuível ao serviço, não qualquer 403 de proxy/rota inexistente.
    if response.status_code not in {401, 403} or not (
        response.headers.get("www-authenticate")
        or response.headers.get("x-amzn-errortype")
        or response.headers.get("x-amzn-requestid")
        or response.headers.get("x-amz-request-id")
    ):
        raise AssertionError(f"EXPECTED_AUTH_DENIAL: status={response.status_code}")
    return {"status": "PASS", "http_status": response.status_code}


def mcp_request():
    return {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "santander-terraform-check", "version": "1.0"},
        },
    }


def observe_unknown_customer_error(result):
    """Um erro genérico da tool não identifica a causa nem comprova autorização."""
    text = "\n".join(block.text for block in result.content if block.type == "text")
    body = json.dumps(result.structuredContent) + text
    if not result.isError or any(key in body for key in ("balance_brl", "display_name")):
        raise AssertionError("UNKNOWN_CUSTOMER_MUST_RETURN_ERROR_WITHOUT_PROFILE")
    return {
        "status": "PASS",
        "scope": "ERROR_WITHOUT_PROFILE",
        "cause": "NOT_PROVEN",
        "error_category": (
            "GATEWAY_INTERNAL_ERROR"
            if "An internal error occurred" in text else "OTHER_TOOL_ERROR"
        ),
    }


def direct_cognito_token(config, session, client_id, *, scope=None):
    """Somente testes de controle: segredo fica em memória e nunca é retornado."""
    endpoint = urlsplit(config["token_endpoint"])
    if (
        endpoint.scheme != "https"
        or not (endpoint.hostname or "").endswith(
            f".auth.{config['region']}.amazoncognito.com"
        )
        or endpoint.path != "/oauth2/token"
        or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
        or endpoint.port not in {None, 443}
    ):
        raise ValueError("INVALID_COGNITO_TOKEN_ENDPOINT")
    client = session.client("cognito-idp").describe_user_pool_client(
        UserPoolId=config["user_pool_id"], ClientId=client_id
    )["UserPoolClient"]
    with httpx.Client(timeout=30, follow_redirects=False) as http:
        response = http.post(
            config["token_endpoint"],
            auth=(client_id, client["ClientSecret"]),
            data={"grant_type": "client_credentials", "scope": scope or config["scope"]},
        )
        if response.status_code != 200:
            raise RuntimeError(f"COGNITO_TOKEN_FAILED: HTTP {response.status_code}")
        return response.json()["access_token"]


async def verify_cloud(config, *, profile, include_llm=False):
    session = boto3.Session(profile_name=profile, region_name=config["region"])
    caller = session.client("sts").get_caller_identity()
    if caller["Account"] != config["account_id"]:
        raise RuntimeError("WRONG_AWS_ACCOUNT")
    gateway = validate_gateway(config["gateway_url"], config["region"])
    checks = {}
    with httpx.Client(timeout=30, follow_redirects=False) as http:
        checks["runtime_anonymous_denied"] = require_denial(http.post(
            runtime_url(config), json={"customer_id": "C001"}
        ))
        for name, headers in (
            ("gateway_anonymous_denied", {}),
            ("gateway_invalid_token_denied", {"Authorization": "Bearer invalid-token"}),
        ):
            checks[name] = require_denial(http.post(
                gateway, json=mcp_request(),
                headers={"Accept": "application/json, text/event-stream", **headers},
            ))
        denied_token = direct_cognito_token(config, session, config["denied_client_id"])
        checks["gateway_wrong_client_denied"] = require_denial(http.post(
            gateway, json=mcp_request(), headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {denied_token}",
            }
        ))
        del denied_token
    # Exercita Identity de forma isolada antes do mesmo caminho dentro do Runtime.
    token = gateway_access_token(session.client("bedrock-agentcore"), config)
    async with connect_gateway(gateway, token) as mcp:
        tools = await list_tools(mcp)
        if {t.name for t in tools} != {TOOL_NAME}:
            raise AssertionError("UNEXPECTED_GATEWAY_CATALOG")
        checks["identity_to_gateway_mcp"] = {"status": "PASS", "tools": [t.name for t in tools]}
        invalid = await mcp.call_tool(TOOL_NAME, {"customer_id": "C999"})
        checks["unknown_customer_error_observed"] = observe_unknown_customer_error(invalid)
    del token
    for customer_id in ("C001", "C002"):
        checks[f"runtime_{customer_id}"] = invoke_runtime(config, session, customer_id=customer_id)
    if include_llm:
        checks["runtime_llm"] = invoke_runtime(config, session, mode="llm")
    return {
        "status": "PASS",
        "mode": "AWS_LIVE",
        "tested_at": datetime.now(UTC).isoformat(),
        "region": config["region"],
        "runtime_zip_sha256": config["runtime_zip_sha256"],
        "checks": checks,
        "llm": "PASS" if include_llm else "NOT_RUN",
    }
