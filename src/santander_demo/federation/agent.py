"""Agente Strands no kernel do notebook; Bedrock e ferramentas executam na AWS."""

from santander_demo.banking.agent import discover as discover_banking
from santander_demo.banking.agent import run_agent as run_banking_agent
from santander_demo.banking.spec import LOBS
from santander_demo.federation.spec import PREFIXES, readable, tools_by_lob


def discover(session, environment):
    return discover_banking(
        session,
        environment["registry_arn"],
        environment["gateway_url"],
        tools_by_lob=tools_by_lob(),
    )


def run_agent(prompt, token, environment, session):
    config = {
        **environment,
        "tools_by_lob": tools_by_lob(),
        "read_tools": [name for lob in LOBS for name in readable(lob, central=True)],
    }
    result = run_banking_agent(prompt, "Bearer " + token, config, session=session)
    for call in result.get("tool_calls", []):
        call["lob"] = next((lob for lob in LOBS if PREFIXES[lob] == call["lob"]), "unknown")
    result["agent_location"] = "NOTEBOOK_KERNEL"
    return result
