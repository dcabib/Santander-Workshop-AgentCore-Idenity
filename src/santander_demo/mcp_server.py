"""Especialista de fraude MCP. stdio local; HTTP apenas atrás do Runtime autenticado."""

import argparse
import json
import logging

from mcp.server.fastmcp import FastMCP

from santander_demo.backends import execute

mcp = FastMCP("santander-fraude", host="0.0.0.0", port=8000, stateless_http=True)


@mcp.tool()
def consultar_fraude(cliente_id: str, max_registros: int) -> dict:
    """Indícios de fraude exclusivamente sintéticos, com limite de 50 registros."""
    result = execute(
        "fraude___consultar_fraude", {"cliente_id": cliente_id, "max_registros": max_registros}
    )
    logging.getLogger("santander").warning(
        json.dumps(
            {
                "event": "synthetic_tool_executed",
                "tool": "fraude___consultar_fraude",
            }
        )
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
