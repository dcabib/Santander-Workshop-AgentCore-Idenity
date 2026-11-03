"""Cedar real: sintaxe, matriz pessoa/aplicação e limites de cada ferramenta."""

import json

import cedarpy
import pytest

from infra.workshop.generate import bindings, federation_bindings, generate
from santander_demo.aws_workshop.contracts import RISK, TOOLS, policies

GATEWAY = "arn:aws:bedrock-agentcore:us-east-1:111111111111:gateway/test"
ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Test"
USERS = {label: f"subject-{label}" for label in "abcd"}
CLIENTS = {"supervisor": "client-supervisor", "riscos": "client-riscos"}
DOCUMENT = "\n".join(policies(GATEWAY, ISSUER, *CLIENTS.values(), USERS).values())
PARSED = cedarpy.PolicySet.from_str(DOCUMENT)


def decision(label, application, tool, arguments, *, changes=None, prefix=""):
    principal = {"type": "AgentCore::OAuthUser", "id": USERS.get(label, label)}
    tags = {"iss": ISSUER, "aud": CLIENTS.get(application, application), "token_use": "id"}
    tags.update(changes or {})
    tags = {key: value for key, value in tags.items() if value is not None}
    result = cedarpy.is_authorized(
        {
            "principal": principal,
            "action": {"type": "AgentCore::Action", "id": prefix + tool},
            "resource": {"type": "AgentCore::Gateway", "id": GATEWAY},
            "context": {"input": arguments},
        },
        PARSED if not prefix else DOCUMENT.replace(
            'AgentCore::Action::"', f'AgentCore::Action::"{prefix}',
        ),
        [{"uid": principal, "attrs": {}, "parents": [], "tags": tags}],
    )
    assert not result.diagnostics.errors, result.diagnostics.errors
    return result.allowed


@pytest.mark.parametrize("prefix", ["", "retail___", "transaction___", "lending___"])
@pytest.mark.parametrize("label", ["a", "b", "c", "d", "unknown"])
@pytest.mark.parametrize("application", ["supervisor", "riscos", "unknown"])
@pytest.mark.parametrize("tool", ["riscos___consultar_risco", "especialista___consultar_fraude"])
def test_person_application_and_federation_boundaries(label, application, tool, prefix):
    want = (
        label in "ac" and application in CLIENTS if tool.startswith("riscos")
        else label in "bc" and application == "supervisor"
    )
    assert decision(label, application, tool, {
        "cliente_id": "C001", "max_registros": 1,
    }, prefix=prefix) == want


@pytest.mark.parametrize("label", "abcd")
@pytest.mark.parametrize("application", CLIENTS)
@pytest.mark.parametrize("table", ["riscos", "fraude", "k2", "unknown"])
@pytest.mark.parametrize("tool", ["consultar_tabela", "memorizar_referencia"])
def test_source_tools_keep_gateway_boundaries(label, application, table, tool):
    want = (
        label in "abc" and table in {"riscos", "k2"}
        or label in "bc" and application == "supervisor" and table == "fraude"
    )
    assert decision(label, application, "especialista___" + tool, {"tabela": table}) == want


@pytest.mark.parametrize("changes", [
    {"iss": "https://other.invalid"}, {"iss": None},
    {"aud": "other"}, {"aud": None},
    {"token_use": "access"}, {"token_use": None},
])
def test_untrusted_or_missing_claims_deny(changes):
    assert not decision("c", "supervisor", "riscos___consultar_risco", {
        "cliente_id": "C001", "max_registros": 1,
    }, changes=changes)


@pytest.mark.parametrize("customer,limit", [("C002", 1), ("C001", 0), ("C001", 11)])
def test_input_limits_deny(customer, limit):
    assert not decision("c", "supervisor", "riscos___consultar_risco", {
        "cliente_id": customer, "max_registros": limit,
    })


@pytest.mark.parametrize("document", [bindings(), federation_bindings()])
def test_every_cloudformation_policy_parses(document):
    statements = [
        item["Properties"]["Definition"]["Cedar"]["Statement"]["Fn::Sub"]
        for item in document["Resources"].values()
        if item["Type"] == "AWS::BedrockAgentCore::Policy"
    ]
    assert statements
    for statement in statements:
        assert json.loads(cedarpy.policies_to_json_str(statement))


def test_cedar_typechecks_against_the_declared_mcp_inputs():
    schema = {"AgentCore": {
        "entityTypes": {
            "OAuthUser": {"shape": {"type": "Record", "attributes": {}}, "tags": {"type": "String"}},
            "Gateway": {"shape": {"type": "Record", "attributes": {}}},
        },
        "actions": {},
    }}
    for prefix in ["", "retail___", "transaction___", "lending___"]:
        for name, tool in [
            ("riscos___" + RISK["name"], RISK),
            *[("especialista___" + tool["name"], tool) for tool in TOOLS],
        ]:
            attributes = {
                name: {
                    "type": {"integer": "Long", "string": "String"}[spec["type"]],
                    "required": name in tool["inputSchema"]["required"],
                }
                for name, spec in tool["inputSchema"]["properties"].items()
            }
            schema["AgentCore"]["actions"][prefix + name] = {"appliesTo": {
                "principalTypes": ["OAuthUser"], "resourceTypes": ["Gateway"],
                "context": {"type": "Record", "attributes": {
                    "input": {"type": "Record", "attributes": attributes},
                }},
            }}
        text = DOCUMENT.replace('AgentCore::Action::"', f'AgentCore::Action::"{prefix}')
        validation = cedarpy.validate_policies(text, schema)
        assert validation.validation_passed, validation


def test_generator_rejects_invalid_cedar_before_writing(monkeypatch, tmp_path):
    import infra.workshop.generate as generator

    original = generator.bindings

    def invalid():
        document = original()
        statement = document["Resources"]["AllowRisk"]["Properties"]["Definition"]["Cedar"]
        statement["Statement"]["Fn::Sub"] = (
            'permit(principal in [AgentCore::OAuthUser::"a"], action, resource);'
        )
        return document

    monkeypatch.setattr(generator, "bindings", invalid)
    with pytest.raises(ValueError):
        generate(tmp_path)
    assert not list(tmp_path.iterdir())
