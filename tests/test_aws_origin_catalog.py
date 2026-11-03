import json
from copy import deepcopy

import pytest

from infra.registry_workflow.generate import publish, transition
from santander_demo.aws_workshop.catalog import origin_bundle, validate_origin_record

IDENTITY = {"Issuer": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
            "SupervisorClientId": "supervisor", "RiscosClientId": "riscos"}
GATEWAY = "https://hub.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
RUNTIMES = {
    key: f"arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/origin_{key}"
    for key in ["Riscos", "Fraude"]
}


def test_two_real_http_records_have_distinct_clients_and_iac_endpoints():
    package = origin_bundle(IDENTITY, GATEWAY, RUNTIMES)
    for label, client in [("Riscos", "riscos"), ("Fraude", "supervisor")]:
        record = package[label]
        data = json.loads(record["descriptors"]["custom"]["data"])
        assert data["authentication"] == "COGNITO_JWT" and data["protocol"] == "HTTP"
        assert data["audience"] == client and data["gatewayUrl"] == GATEWAY
        assert data["sourceKind"] == "AWS_SIMULATED_DATABRICKS"
        assert validate_origin_record(record, package[label]) == RUNTIMES[label]


@pytest.mark.parametrize("field", ["runtimeArn", "gatewayUrl", "issuer", "audience", "authentication"])
def test_catalog_cannot_redirect_credentials_or_change_identity_contract(field):
    expected = origin_bundle(IDENTITY, GATEWAY, RUNTIMES)["Riscos"]
    record = deepcopy(expected)
    data = json.loads(record["descriptors"]["custom"]["data"])
    data[field] = "attacker-controlled"
    record["descriptors"]["custom"]["data"] = json.dumps(data, sort_keys=True)
    with pytest.raises(ValueError, match="UNTRUSTED_ORIGIN_DESCRIPTOR"):
        validate_origin_record(record, expected)


def test_origin_templates_preserve_separate_publication_and_digest_review():
    names = ("Riscos", "Fraude")
    assert set(publish(names)["Resources"]) == set(names)
    for approve in [False, True]:
        document = transition(approve, names)
        for label, resource in document["Resources"].items():
            props = resource["Properties"]
            assert props["Kind"] == ("Approval" if approve else "Submission")
            if approve:
                assert props["ReviewedDigest"] == {"Ref": label + "Digest"}
                assert props["Decision"] == {"Ref": label + "Decision"}
    assert set(publish()["Resources"]) == {"Mcp", "Agent"}
