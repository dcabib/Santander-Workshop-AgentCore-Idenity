"""Contrato compartilhado pelos templates, testes Cedar e notebook."""

import json

import cedarpy

from santander_demo.banking.spec import DELETE_TOOL, LOBS, WRITE_TOOLS, data_file

ACCOUNTS = ("platform", *LOBS)
PREFIXES = {lob: value["module"] for lob, value in LOBS.items()}
SCOPE = "access_as_user"
WHOAMI = {
    "name": "whoami",
    "description": "Verify the delegated identity received by this account's MCP Runtime.",
    "inputSchema": {"type": "object", "properties": {}},
}


def schemas(lob):
    return [*data_file("tools.json")[lob], WHOAMI]


def local_name(tool):
    return "backend___" + tool


def central_name(lob, tool):
    return PREFIXES[lob] + "___" + local_name(tool)


def tools_by_lob():
    return {lob: [central_name(lob, t["name"]) for t in schemas(lob)] for lob in LOBS}


def readable(lob, *, central):
    return [
        central_name(lob, t["name"]) if central else local_name(t["name"])
        for t in schemas(lob)
        if lob + "___" + t["name"] not in WRITE_TOOLS | {DELETE_TOOL}
    ]


def cedar(account, gateway_arn, tenant, caller, allowed_users):
    """Um engine independente por conta. Scope exato, tid, oid e azp obrigatórios.

    Este lab emite só access_as_user. A comparação exata falha fechada se o tenant
    emitir scopes adicionais; não faz matching parcial de scopes.
    """
    q = json.dumps
    central = account == "platform"
    actions = [
        action
        for lob in (LOBS if central else [account])
        for action in readable(lob, central=central)
    ]
    listed = ",\n    ".join("AgentCore::Action::" + q(name) for name in actions)
    result = {
        "ReadDelegated": f"""permit(
  principal is AgentCore::OAuthUser,
  action in [{listed}],
  resource == AgentCore::Gateway::{q(gateway_arn)}
)
when {{
  principal.hasTag("tid") && principal.getTag("tid") == {q(tenant)} &&
  principal.hasTag("azp") && principal.getTag("azp") == {q(caller)} &&
  principal.hasTag("oid") && {q(allowed_users)}.contains(principal.getTag("oid")) &&
  principal.hasTag("scp") && principal.getTag("scp") == {q(SCOPE)}
}};"""
    }
    if central or account == "retail-banking":
        name = (
            central_name("retail-banking", "delete_customer")
            if central
            else local_name("delete_customer")
        )
        result["NeverDelete"] = f"""forbid(
  principal,
  action == AgentCore::Action::{q(name)},
  resource == AgentCore::Gateway::{q(gateway_arn)}
);"""
        # Duas negativas separadas, sem modificar policies durante a demo.
        name = (
            central_name("retail-banking", "get_profile") if central else local_name("get_profile")
        )
        customer = "C007" if central else "C008"
        result["BoundaryDemo"] = f"""forbid(
  principal,
  action == AgentCore::Action::{q(name)},
  resource == AgentCore::Gateway::{q(gateway_arn)}
)
when {{ context.input.customer_id == {q(customer)} }};"""
    return result


def evaluate(account, claims, tool, arguments, *, gateway_arn, tenant, caller, users):
    """Avaliador Cedar LOCAL; não simula troca OAuth nem execução AWS."""
    principal = {"type": "AgentCore::OAuthUser", "id": claims.get("sub", "missing")}
    tags = {
        key: value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
        for key, value in claims.items()
        if value is not None
    }
    result = cedarpy.is_authorized(
        {
            "principal": principal,
            "action": {"type": "AgentCore::Action", "id": tool},
            "resource": {"type": "AgentCore::Gateway", "id": gateway_arn},
            "context": {"input": arguments},
        },
        "\n\n".join(cedar(account, gateway_arn, tenant, caller, users).values()),
        [{"uid": principal, "attrs": {}, "parents": [], "tags": tags}],
    )
    return result.allowed


def local_matrix():
    """Prova a independência das duas Policies usando o mesmo Cedar do IaC."""
    rows = []
    base = {"sub": "local-sub", "oid": "user-demo", "tid": "tenant-demo", "scp": SCOPE}
    for customer, expected in [
        ("C003", (True, True)),
        ("C007", (False, True)),
        ("C008", (True, False)),
    ]:
        decisions = []
        for account, caller in [("platform", "notebook-app"), ("retail-banking", "platform-app")]:
            decisions.append(
                evaluate(
                    account,
                    {**base, "azp": caller},
                    central_name("retail-banking", "get_profile")
                    if account == "platform"
                    else local_name("get_profile"),
                    {"customer_id": customer},
                    gateway_arn="arn:local:" + account,
                    tenant="tenant-demo",
                    caller=caller,
                    users=["user-demo"],
                )
            )
        if tuple(decisions) != expected:
            raise AssertionError("LOCAL_POLICY_CONTRACT_MISMATCH")
        rows.append(
            {
                "customer": customer,
                "platform_policy": "ALLOW" if decisions[0] else "DENY",
                "retail_policy_isolated": "ALLOW" if decisions[1] else "DENY",
                "end_to_end_contract": "ALLOW" if all(decisions) else "DENY",
            }
        )
    return {"mode": "LOCAL_CEDAR_ONLY", "oauth_and_aws": "NOT_RUN", "cases": rows}
