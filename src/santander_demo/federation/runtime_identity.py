"""Ferramenta de evidência OBO, ativada apenas no Runtime do notebook 11."""

import os

from mcp.server.fastmcp import Context

from santander_demo.federation.spec import SCOPE
from santander_demo.identity import verify_entra


def verify_runtime_identity(authorization, config):
    if not authorization.startswith("Bearer "):
        raise ValueError("DELEGATED_TOKEN_REQUIRED")
    identity = verify_entra(
        authorization[7:],
        tenant=config["tenant"],
        audience=config["audience"],
        version="2.0",
    )
    if (
        identity.claims.get("azp") != config["caller"]
        or identity.claims.get("scp") != SCOPE
        or not identity.claims.get("oid")
        or identity.claims.get("ver") != "2.0"
    ):
        raise ValueError("RUNTIME_DELEGATION_MISMATCH")
    return {
        "mode": "AWS_VERIFIED_JWT",
        "lob": config["lob"],
        **identity.summary(),
    }


def register(mcp):
    import json

    config = json.loads(os.environ["FEDERATED_IDENTITY"])

    @mcp.tool()
    def whoami(ctx: Context) -> dict:
        """Verify the delegated identity received by this account's MCP Runtime."""
        request = ctx.request_context.request
        authorization = request.headers.get("authorization", "") if request else ""
        return verify_runtime_identity(authorization, config)
