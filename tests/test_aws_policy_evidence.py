import json
from types import SimpleNamespace

import pytest

from santander_demo.aws_workshop.evidence import backend_event, correlate_policy


def native(request="native", tool="riscos___consultar_risco", decision="DENY"):
    return {
        "eventId": request + "-policy",
        "message": json.dumps({
            "request_id": request,
            "body": {"log": "Tool: " + tool, "policy": {"decision": decision}},
        }),
    }


def backend(request="correlation"):
    return {
        "eventId": "backend",
        "message": "[INFO]\t" + json.dumps({"event": "backend_invoked", "request_id": request}),
    }


def fixture(gateway=None, backend_logs=None, expected="DENY"):
    class Logs:
        def get_paginator(self, operation):
            assert operation == "filter_log_events"
            return self

        def paginate(self, **kwargs):
            # Empty pages must not terminate collection.
            values = gateway if kwargs["logGroupName"] == "gateway" else backend_logs
            return [{"events": [], "nextToken": "cursor"}, {"events": values or []}]

    lab = SimpleNamespace(
        aws=SimpleNamespace(client=lambda _: Logs()),
        gateway={"GatewayLogGroup": "gateway", "RiskLogGroup": "risk"},
        backend={"RuntimeLogGroup": "runtime"},
    )
    rows = [{
        "tool": "riscos___consultar_risco", "expected": expected,
        "evidence": {"request_id": "correlation", "gateway_request_ids": ["native"]},
    }]
    return lab, rows


def test_empty_pages_are_followed_and_native_denial_is_correlated():
    lab, rows = fixture([native()])
    correlate_policy(lab, rows, 123)
    assert rows[0]["correlation"]["native_policy_verified"]
    assert not rows[0]["correlation"]["backend_observed"]


@pytest.mark.parametrize("gateway", [
    [], [native(request="other")], [native(tool="wrong")], [native(decision="ALLOW")],
    [native(), native(decision="ALLOW")],
])
def test_missing_wrong_or_conflicting_decision_cannot_pass(gateway):
    lab, rows = fixture(gateway)
    correlate_policy(lab, rows, 123)
    assert not rows[0]["correlation"]["native_policy_verified"]


def test_denial_with_backend_execution_is_a_hard_failure():
    lab, rows = fixture([native()], [backend()])
    with pytest.raises(AssertionError, match="POLICY_DENIAL_EXECUTED_BACKEND"):
        correlate_policy(lab, rows, 123)


def test_allow_requires_separate_backend_evidence():
    lab, rows = fixture([native(decision="ALLOW")], [backend()], expected="ALLOW")
    correlate_policy(lab, rows, 123)
    assert rows[0]["correlation"]["native_policy_verified"]
    assert rows[0]["correlation"]["backend_observed"]


@pytest.mark.parametrize("message", [
    "connection failure", "{broken", '{"event":"other","request_id":"correlation"}',
    '{"event":"backend_invoked","request_id":"different"}',
])
def test_unrelated_or_malformed_log_is_not_execution(message):
    assert not backend_event({"message": message}, "correlation")
