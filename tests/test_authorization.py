import time
from dataclasses import replace

import pytest

from santander_demo.contracts import CLIENTE, DemoError
from santander_demo.identity import LocalIssuer
from santander_demo.local import Workshop
from santander_demo.policy import PolicyContract, authorize
from santander_demo.registry import Record, checked_endpoint

ARGS = {"cliente_id": CLIENTE, "max_registros": 50}


def test_acceptance_matrix_denied_requests_never_execute():
    rows = Workshop().policy_matrix()
    assert len(rows) == 12 and all(row["passed"] for row in rows)


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "wrong"},
        {"iss": "https://attacker.invalid"},
        {"tid": "another"},
        {"exp": int(time.time()) - 100},
        {"iat": int(time.time()) + 600},
        {"exp": None},
    ],
)
def test_jwt_rejects_wrong_boundary(changes):
    lab = Workshop()
    with pytest.raises(DemoError):
        lab.call(lab.idp.token(**changes), "riscos___consultar_risco", ARGS)
    assert lab.evidence.backend_invocations == 0


def test_same_claims_signed_by_different_issuer_rejected():
    lab = Workshop()
    with pytest.raises(DemoError, match="AUTH_INVALID_TOKEN"):
        lab.call(LocalIssuer().token(), "riscos___consultar_risco", ARGS)


@pytest.mark.parametrize(
    "patch",
    [
        {"agent_name": "supervisor"},
        {"approval": True},
        {"department": "fraude"},
        {"max_registros": True},
        {"max_registros": 1.5},
        {"max_registros": 0},
        {"cliente_id": "real-customer"},
    ],
)
def test_tool_arguments_cannot_supply_identity(patch):
    lab = Workshop()
    with pytest.raises(DemoError, match="SCHEMA_INVALID"):
        lab.call(lab.idp.token(), "riscos___consultar_risco", {**ARGS, **patch})
    assert lab.evidence.backend_invocations == 0


def test_cedar_exact_action_resource_and_caller():
    lab = Workshop()
    who = lab.idp.verifier.verify(lab.idp.token())
    assert authorize(who, "riscos___consultar_risco", ARGS).allowed
    assert not authorize(who, "other___consultar_risco", ARGS).allowed
    # Políticas de outro Gateway não podem liberar o Gateway deste request.
    import cedarpy

    from santander_demo.policy import render

    request = {
        "principal": {"type": "AgentCore::OAuthUser", "id": "user-riscos"},
        "action": {"type": "AgentCore::Action", "id": "riscos___consultar_risco"},
        "resource": {"type": "AgentCore::Gateway", "id": "another-gateway"},
        "context": {"input": ARGS},
    }
    entity = {
        "uid": request["principal"],
        "attrs": {},
        "parents": [],
        "tags": {k: v for k, v in who.claims.items() if isinstance(v, str)},
    }
    assert not cedarpy.is_authorized(request, render(PolicyContract()), [entity]).allowed
    near_match = lab.idp.verifier.verify(lab.idp.token(caller="supervisor-untrusted"))
    assert not authorize(near_match, "riscos___consultar_risco", ARGS).allowed


def test_entra_v1_contract_is_explicit():
    lab = Workshop()
    lab.policy = replace(lab.policy, caller_claim="appid")
    with pytest.raises(DemoError, match="POLICY_DENY"):
        lab.call(lab.idp.token(), "riscos___consultar_risco", ARGS)
    result = lab.call(
        lab.idp.token(azp=None, appid="supervisor", ver="1.0"), "riscos___consultar_risco", ARGS
    )
    assert result["synthetic"]


def test_empty_delegated_scope_is_not_a_user_delegation():
    lab = Workshop()
    with pytest.raises(DemoError, match="POLICY_DENY"):
        lab.call(lab.idp.token(scp=""), "riscos___consultar_risco", ARGS)


def test_registry_approval_is_not_execution_permission():
    lab = Workshop()
    assert lab.registry.search("fraude")
    result = lab.analyze(lab.idp.token("riscos"))
    assert result["results"][-1]["outcome"] == "POLICY_DENY"
    assert not lab.registry.search("rascunho")
    assert not lab.registry.search("rejeitado")


def test_registry_separates_roles_and_transitions():
    lab = Workshop()
    lab.registry.publish(Record("new", "new", "nova"), "publisher")
    with pytest.raises(DemoError):
        lab.registry.decide("new", "APPROVED", "approver")
    lab.registry.submit("new", "publisher")
    with pytest.raises(DemoError, match="REGISTRY_APPROVAL_DENIED"):
        lab.registry.decide("new", "APPROVED", "publisher")
    with pytest.raises(DemoError):
        lab.registry.publish(Record("consumer-write", "new", "nova"), "consumer")
    lab.registry.decide("new", "APPROVED", "approver")
    assert lab.registry.search("nova")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://trusted/mcp",
        "https://evil/mcp",
        "https://trusted/mcp/../evil",
        "https://user:secret@trusted/mcp",
        "https://trusted/mcp#evil",
    ],
)
def test_no_bearer_to_registry_supplied_untrusted_url(endpoint):
    with pytest.raises(DemoError, match="UNTRUSTED_ENDPOINT"):
        checked_endpoint(endpoint, {"https://trusted/mcp"})


def test_evidence_has_no_bearer_or_personal_identity():
    import json

    lab = Workshop()
    token = lab.idp.token("ambos")
    lab.analyze(token)
    text = json.dumps(lab.evidence.export())
    assert token not in text and "user-ambos" not in text
    assert "LOCAL_SIMULATION" in text
