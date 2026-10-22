"""Contrato público da adaptação do artigo; nenhuma chamada AWS ao importar."""

import json
from importlib.resources import files

ARTICLE = "https://aws.amazon.com/blogs/machine-learning/build-a-multi-account-ai-agent-with-agentcore-gateway-and-mcp/"
UPSTREAM = (
    "https://github.com/aws-samples/sample-amazon-bedrock-agentcore-banking-mcp-multi-account"
)
COMMIT = "f76491b63d005d1ad0c253396f58f67da021f94d"
LOBS = {
    "retail-banking": {"module": "retail", "description": "Customers, accounts and balances"},
    "transaction-banking": {
        "module": "transaction",
        "description": "Payments, transfers and beneficiaries",
    },
    "lending-wealth": {
        "module": "lending",
        "description": "Loans, credit scores, eligibility and policy retrieval",
    },
}
WRITE_TOOLS = {
    "retail-banking___update_balance",
    "transaction-banking___transfer_funds",
    "transaction-banking___schedule_payment",
}
DELETE_TOOL = "retail-banking___delete_customer"
TABLE_KEYS = {
    "Customers": ("customer_id", None),
    "Accounts": ("account_id", None),
    "Balances": ("account_id", None),
    "Payments": ("payment_id", None),
    "Beneficiaries": ("beneficiary_id", None),
    "Loans": ("loan_id", None),
    "CreditScores": ("customer_id", None),
    "EMISchedule": ("loan_id", "emi_number"),
}


def data_file(name):
    return json.loads(files("santander_demo.banking").joinpath("data", name).read_text())


def qualified_tools():
    return [
        f"{lob}___{tool['name']}"
        for lob, tools in data_file("tools.json").items()
        for tool in tools
    ]


def cedar(gateway_arn):
    """Mesma fronteira do artigo: usuário no Gateway, M2M nos destinos."""
    actions = qualified_tools()
    read = [name for name in actions if name not in WRITE_TOOLS | {DELETE_TOOL}]

    def permit(names):
        values = ",\n    ".join("AgentCore::Action::" + json.dumps(name) for name in names)
        return f"""permit(
  principal is AgentCore::OAuthUser,
  action in [{values}],
  resource == AgentCore::Gateway::{json.dumps(gateway_arn)}
);"""

    return {
        "ReadTools": permit(read),
        "WriteTools": permit(sorted(WRITE_TOOLS)),
        "NeverDelete": f"""forbid(
  principal,
  action == AgentCore::Action::{json.dumps(DELETE_TOOL)},
  resource == AgentCore::Gateway::{json.dumps(gateway_arn)}
);""",
    }
