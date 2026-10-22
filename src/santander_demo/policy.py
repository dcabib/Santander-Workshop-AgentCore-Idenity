"""A mesma fonte Cedar é usada no avaliador local e no CloudFormation."""

import json
from dataclasses import dataclass

import cedarpy

from santander_demo.contracts import LOCAL_GATEWAY_ARN, TOOLS
from santander_demo.identity import Identity


@dataclass(frozen=True)
class PolicyContract:
    gateway_arn: str = LOCAL_GATEWAY_ARN
    tenant: str = "tenant-demo"
    caller_claim: str = "azp"
    risks_users: tuple[str, ...] = ("user-riscos", "user-ambos", "user-sem-grant")
    fraud_users: tuple[str, ...] = ("user-ambos",)
    risks_callers: tuple[str, ...] = ("supervisor", "riscos")
    fraud_callers: tuple[str, ...] = ("supervisor", "fraude")

    def __post_init__(self):
        if self.caller_claim not in {"azp", "appid"}:
            raise ValueError("Claim de aplicação deve ser azp (v2) ou appid (v1)")
        if not all((self.risks_users, self.fraud_users, self.risks_callers, self.fraud_callers)):
            raise ValueError("Allowlists vazias: preencha o contrato de identidade")


def statements(contract: PolicyContract) -> dict[str, str]:
    q = json.dumps
    result = {}
    for tool, spec in TOOLS.items():
        fraud = spec["domain"] == "fraude"
        users = contract.fraud_users if fraud else contract.risks_users
        callers = contract.fraud_callers if fraud else contract.risks_callers
        result[tool] = f"""permit(
  principal,
  action == AgentCore::Action::{q(tool)},
  resource == AgentCore::Gateway::{q(contract.gateway_arn)}
)
when {{
  principal.hasTag("tid") &&
  principal.getTag("tid") == {q(contract.tenant)} &&
  principal.hasTag("oid") &&
  {q(list(users))}.contains(principal.getTag("oid")) &&
  principal.hasTag({q(contract.caller_claim)}) &&
  {q(list(callers))}.contains(principal.getTag({q(contract.caller_claim)})) &&
  principal.hasTag("scp") &&
  principal.getTag("scp") != "" &&
  context.input.max_registros >= 1 &&
  context.input.max_registros <= 50
}};"""
    return result


def render(contract: PolicyContract) -> str:
    return "\n\n".join(statements(contract).values())


def authorize(identity: Identity, action: str, arguments: dict, contract=None):
    contract = contract or PolicyContract()
    uid = {"type": "AgentCore::OAuthUser", "id": identity.claims.get("oid", "missing")}
    # A projeção é um contrato LOCAL. A prova de mapeamento nativo é o teste em AWS.
    tags = {k: v for k, v in identity.claims.items() if isinstance(v, str)}
    return cedarpy.is_authorized(
        {
            "principal": uid,
            "action": {"type": "AgentCore::Action", "id": action},
            "resource": {"type": "AgentCore::Gateway", "id": contract.gateway_arn},
            "context": {"input": arguments},
        },
        render(contract),
        [{"uid": uid, "attrs": {}, "parents": [], "tags": tags}],
    )
