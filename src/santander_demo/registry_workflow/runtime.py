"""Agente determinístico HTTP → MCP/SigV4 → Gateway; sem inferência de LLM."""

import json
import os

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .contracts import GATEWAY_TOOL, bundle, risk


class GatewayAuth(httpx.Auth):
    requires_request_body = True

    def __init__(self, url, session):
        self.url, self.session = url, session

    def auth_flow(self, request):
        if str(request.url) != self.url:
            raise ValueError("UNTRUSTED_GATEWAY")
        signed = AWSRequest(
            method=request.method, url=self.url, data=request.content, headers=dict(request.headers)
        )
        SigV4Auth(
            self.session.get_credentials().get_frozen_credentials(),
            "bedrock-agentcore",
            self.session.region_name,
        ).add_auth(signed)
        request.headers.update(dict(signed.headers))
        yield request


async def run(arguments):
    risk(arguments)  # Validação antes de abrir a sessão; não concede autorização.
    url = os.environ["GATEWAY_URL"]
    bundle(gateway_url=url)  # Valida domínio, protocolo e região permitidos.
    session = boto3.Session(region_name="us-east-1")

    def client_factory(**kwargs):
        return httpx.AsyncClient(
            **{**kwargs, "auth": GatewayAuth(url, session), "follow_redirects": False}
        )

    async with streamablehttp_client(url, httpx_client_factory=client_factory) as streams:
        async with ClientSession(streams[0], streams[1]) as mcp:
            await mcp.initialize()
            tools = await mcp.list_tools()
            if GATEWAY_TOOL not in {tool.name for tool in tools.tools}:
                raise ValueError("TOOL_NOT_ADVERTISED")
            result = await mcp.call_tool(GATEWAY_TOOL, arguments)
            if result.isError:
                raise RuntimeError("MCP_TOOL_ERROR")
            values = [json.loads(c.text) for c in result.content if c.type == "text"]
            if len(values) != 1 or values[0] != risk(arguments):
                raise ValueError("UNEXPECTED_TOOL_RESULT")
            data = values[0]
            return {
                "answer": f"Cliente {data['customer_id']}: risco {data['risk']}.",
                "tool": GATEWAY_TOOL,
                "result": data,
            }


if __name__ == "__main__":
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()
    app.entrypoint(run)
    app.run()
