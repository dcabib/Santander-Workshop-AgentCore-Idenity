"""Backend hospedado no Runtime; a fonte sintética e as ACLs vivem no DynamoDB."""

import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime

import boto3
from mcp.server.fastmcp import Context, FastMCP

from .contracts import USER_TOKEN_HEADER
from .identity import actor, verify

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
SOURCE_KIND = "AWS_SIMULATED_DATABRICKS"


def request_id(value):
    return str(uuid.UUID(value))


def session_id(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", value):
        raise ValueError("INVALID_MEMORY_SESSION")
    return value


def verified_source_claims(headers, config):
    authorization = headers.get(USER_TOKEN_HEADER.lower(), "")
    if not authorization.startswith("Bearer "):
        raise ValueError("USER_BEARER_REQUIRED")
    return verify(authorization[7:], config)


class Source:
    def __init__(self, table, memory, memory_id, restricted_client=None):
        self.table, self.memory, self.memory_id = table, memory, memory_id
        self.restricted_client = restricted_client

    def read(self, claims, name):
        if name not in {"riscos", "fraude", "k2"}:
            raise ValueError("UNKNOWN_TABLE")
        if name == "fraude" and self.restricted_client and claims["aud"] == self.restricted_client:
            raise PermissionError("SOURCE_APPLICATION_DENIED")
        # A ACL da fonte é independente da decisão de Cedar no Gateway.
        acl = self.table.get_item(
            Key={"pk": "ACL#" + claims["sub"], "sk": name}, ConsistentRead=True,
        ).get("Item")
        if not acl or not acl.get("allowed"):
            raise PermissionError("SOURCE_PERMISSION_DENIED")
        item = self.table.get_item(
            Key={"pk": "DATA", "sk": name}, ConsistentRead=True,
        ).get("Item")
        if not item:
            raise FileNotFoundError("SOURCE_DATA_MISSING")
        return {
            "source_kind": SOURCE_KIND,
            "synthetic": True,
            "table": name,
            "rows": json.loads(item["content"]),
            "verified_subject": claims["sub"],
        }

    def remember(self, claims, name, session):
        self.read(claims, name)
        event = self.memory.create_event(
            memoryId=self.memory_id,
            actorId=actor(claims),
            sessionId=session_id(session),
            eventTimestamp=datetime.now(UTC),
            payload=[{"conversational": {
                "role": "USER", "content": {"text": json.dumps({"table_reference": name})},
            }}],
        )["event"]
        return {"event_id": event["eventId"], "stored": "reference_only"}

    def recall(self, claims, session):
        arguments = {
            "memoryId": self.memory_id,
            "actorId": actor(claims),
            "sessionId": session_id(session),
            "includePayloads": True,
        }
        names = set()
        while True:
            page = self.memory.list_events(**arguments)
            for event in page.get("events", []):
                for payload in event.get("payload", []):
                    text = payload.get("conversational", {}).get("content", {}).get("text", "")
                    value = json.loads(text)
                    if set(value) != {"table_reference"}:
                        raise ValueError("MEMORY_REFERENCE_INVALID")
                    names.add(value["table_reference"])
            if not page.get("nextToken"):
                break
            arguments["nextToken"] = page["nextToken"]
        result = []
        for name in sorted(names):
            try:
                result.append(self.read(claims, name))
            except (PermissionError, FileNotFoundError):
                # A memória não restaura um documento revogado ou excluído.
                continue
        return {"actor_ref": actor(claims)[:12], "references_seen": len(names), "documents": result}


def risk(event, context):
    from santander_demo.registry_workflow.contracts import risk as query

    request = request_id(event["request_id"])
    if event["cliente_id"] != "C001" or not 1 <= event["max_registros"] <= 10:
        raise ValueError("INVALID_QUERY")
    data = query({"customer_id": event["cliente_id"]})
    LOG.info(json.dumps({"event": "backend_invoked", "request_id": request, "tool": "risco"}))
    return {**data, "synthetic": True, "request_id": request}


def create_server(config=None, source=None):
    config = config or json.loads(os.environ["WORKSHOP_BACKEND"])
    source = source or Source(
        boto3.resource("dynamodb").Table(config["table"]),
        boto3.client("bedrock-agentcore"),
        config["memory_id"],
        config["clients"][1],
    )
    mcp = FastMCP("Santander AWS", host="0.0.0.0", port=8000, stateless_http=True)

    def principal(ctx, correlation):
        request = ctx.request_context.request
        claims = verified_source_claims(request.headers if request else {}, config)
        LOG.info(json.dumps({
            "event": "backend_invoked", "request_id": request_id(correlation),
            "actor_ref": actor(claims)[:12],
        }))
        return claims

    @mcp.tool()
    def consultar_fraude(cliente_id: str, max_registros: int, request_id: str, ctx: Context) -> dict:
        """Consulta os sinais sintéticos de fraude com ACL independente na fonte."""
        claims = principal(ctx, request_id)
        if cliente_id != "C001" or not 1 <= max_registros <= 10:
            raise ValueError("INVALID_QUERY")
        return source.read(claims, "fraude")

    @mcp.tool()
    def consultar_tabela(tabela: str, request_id: str, ctx: Context) -> dict:
        """Consulta tabelas sintéticas no simulador de Databricks hospedado na AWS."""
        return source.read(principal(ctx, request_id), tabela)

    @mcp.tool()
    def identidade_fonte(request_id: str, ctx: Context) -> dict:
        """Equivalente didático a current_user(); não executa Databricks/Unity Catalog reais."""
        claims = principal(ctx, request_id)
        return {"source_kind": SOURCE_KIND, "verified_subject": claims["sub"]}

    @mcp.tool()
    def memorizar_referencia(tabela: str, session_id: str, request_id: str, ctx: Context) -> dict:
        """AgentCore Memory guarda a referência; conteúdo permanece na fonte com ACL."""
        return source.remember(principal(ctx, request_id), tabela, session_id)

    @mcp.tool()
    def recuperar_memoria(session_id: str, request_id: str, ctx: Context) -> dict:
        """Isola actor por issuer/sub e revalida as permissões atuais."""
        return source.recall(principal(ctx, request_id), session_id)

    return mcp
