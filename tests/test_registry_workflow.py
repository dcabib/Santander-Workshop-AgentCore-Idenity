import copy
import json
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters

from infra.registry_workflow.generate import foundation
from santander_demo.registry_workflow.client import RegistryLab
from santander_demo.registry_workflow.contracts import (
    LOCAL_GATEWAY,
    LOCAL_RUNTIME,
    LocalLifecycle,
    bundle,
    digest,
    risk,
    validate_agent,
)
from santander_demo.registry_workflow.provider import Provider


@pytest.mark.parametrize("persona", ["desenvolvedor", "aprovador", "consumidor"])
def test_only_publisher_publishes(persona):
    lab = LocalLifecycle()
    with pytest.raises(PermissionError, match="PUBLISH_DENIED"):
        lab.publish(persona, bundle()["AGENT"])
    assert not lab.records


@pytest.mark.parametrize("persona", ["desenvolvedor", "publicador", "consumidor"])
def test_only_approver_decides(persona):
    lab, package = LocalLifecycle(), bundle()["AGENT"]
    key = lab.publish("publicador", package)
    lab.submit("publicador", key)
    with pytest.raises(PermissionError, match="REVIEW_DENIED"):
        lab.review(persona, key, "APPROVED", digest(package))
    assert lab.discover() == []


def test_lifecycle_and_invocation_are_independent():
    lab, package = LocalLifecycle(), bundle()["AGENT"]
    key = lab.publish("publicador", package)
    assert lab.discover() == []
    lab.submit("publicador", key)
    assert lab.discover() == []
    lab.review("aprovador", key, "APPROVED", digest(package))
    (record,) = lab.discover()
    with pytest.raises(PermissionError, match="INVOKE_DENIED"):
        lab.execute(record, {"customer_id": "C001"}, can_invoke=False)
    assert lab.calls == 0
    assert (
        lab.execute(record, {"customer_id": "C001"}, can_invoke=True)["result"]["risk"] == "baixo"
    )
    assert lab.calls == 1


def test_rejected_record_hidden_and_review_pinned():
    lab, package = LocalLifecycle(), bundle()["AGENT"]
    key = lab.publish("publicador", package)
    lab.submit("publicador", key)
    with pytest.raises(ValueError, match="REVIEW_CHANGED"):
        lab.review("aprovador", key, "APPROVED", "wrong")
    lab.review("aprovador", key, "REJECTED", digest(package))
    assert lab.discover() == []
    with pytest.raises(ValueError, match="IMMUTABLE_VERSION"):
        lab.publish("publicador", package)


def test_descriptor_never_selects_arbitrary_target():
    record = bundle()["AGENT"]
    changed = copy.deepcopy(record)
    changed["descriptors"]["custom"]["data"] = '{"runtimeArn":"attacker"}'
    with pytest.raises(ValueError, match="UNTRUSTED"):
        validate_agent(
            changed, gateway_url=LOCAL_GATEWAY, runtime_arn=LOCAL_RUNTIME, version="1.0.0"
        )
    assert (
        validate_agent(
            record, gateway_url=LOCAL_GATEWAY, runtime_arn=LOCAL_RUNTIME, version="1.0.0"
        )
        == LOCAL_RUNTIME
    )


@pytest.mark.parametrize(
    "data", [{"customer_id": "real-id"}, {"customer_id": "C001", "user": "admin"}, {}]
)
def test_backend_validates_input(data):
    from jsonschema import ValidationError

    with pytest.raises(ValidationError):
        risk(data)


def event(kind, **props):
    return {
        "RequestType": "Create",
        "StackId": "stack",
        "LogicalResourceId": "test",
        "ResourceProperties": {"Kind": kind, **props},
    }


def test_provider_payloads_match_current_aws_sdk():
    client = boto3.Session(
        region_name="us-east-1", aws_access_key_id="testing", aws_secret_access_key="testing"
    ).client("agent-registry-control")
    model = client.meta.service_model
    fake = Mock()
    fake.create_registry.return_value = {
        "registryArn": "arn:aws:agent-registry:us-east-1:000000000000:registry/reg"
    }
    fake.get_registry.return_value = {"status": "READY"}
    p = Provider(fake)
    p.handle(event("Registry"))
    validate_parameters(
        fake.create_registry.call_args.kwargs, model.operation_model("CreateRegistry").input_shape
    )
    for package in bundle().values():
        fake.create_registry_record.return_value = {
            "recordArn": "arn:aws:agent-registry:us-east-1:000000000000:registry/reg/record/id"
        }
        fake.get_registry_record.return_value = {**package, "status": "DRAFT"}
        p.handle(event("Record", RegistryId="registry-1234567890", Package=json.dumps(package)))
        validate_parameters(
            fake.create_registry_record.call_args.kwargs,
            model.operation_model("CreateRegistryRecord").input_shape,
        )


def test_provider_digest_blocks_stale_review_before_write():
    fake = Mock()
    fake.get_registry_record.return_value = {**bundle()["AGENT"], "status": "PENDING_APPROVAL"}
    with pytest.raises(ValueError, match="REVIEW_CHANGED"):
        Provider(fake).handle(
            event(
                "Approval",
                RegistryId="reg",
                RecordId="id",
                Decision="APPROVED",
                ReviewedDigest="stale",
            )
        )
    fake.update_registry_record_status.assert_not_called()


def test_provider_submission_idempotent_and_no_delete_reversal():
    fake = Mock()
    fake.get_registry_record.return_value = {"status": "APPROVED"}
    p = Provider(fake)
    p.handle(event("Submission", RegistryId="reg", RecordId="id"))
    fake.submit_registry_record_for_approval.assert_not_called()
    delete = event("Approval")
    delete.update(RequestType="Delete", PhysicalResourceId="Approval-id")
    p.handle(delete)
    fake.update_registry_record_status.assert_not_called()


def test_provider_delete_waits_until_absent():
    fake = Mock()
    fake.get_registry_record.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "GetRegistryRecord"
    )
    e = event("Record")
    e.update(
        RequestType="Delete",
        PhysicalResourceId="arn:aws:agent-registry:us-east-1:000000000000:registry/reg/record/id",
    )
    Provider(fake).handle(e)
    fake.delete_registry_record.assert_called_once_with(registryId="reg", recordId="id")


def test_pagination_empty_page_and_partial_get_errors():
    lab = RegistryLab.__new__(RegistryLab)
    lab.config = {"RegistryId": "reg"}
    session = Mock()
    client = session.client.return_value
    client.list_discoverable_registry_records.side_effect = [
        {"registryRecords": [], "nextToken": "next"},
        {"registryRecords": [{"recordId": "one"}]},
    ]
    client.batch_get_discoverable_registry_record.return_value = {
        "registryRecords": [],
        "errors": [{"errorCode": "AccessDenied"}],
    }
    with pytest.raises(PermissionError, match="PARTIAL"):
        lab.discover(session)
    assert client.list_discoverable_registry_records.call_count == 2


def test_real_roles_and_iam_gates_in_template():
    r = foundation()["Resources"]

    def actions(role):
        return {
            a
            for p in r[role]["Properties"]["Policies"]
            for st in p["PolicyDocument"]["Statement"]
            for a in st["Action"]
        }

    assert "agent-registry:UpdateRegistryRecordStatus" not in actions("PublisherRole")
    assert "agent-registry:CreateRegistryRecord" not in actions("ApproverRole")
    assert "agent-registry:CreateRegistryRecord" not in actions("DeveloperRole")
    assert "bedrock-agentcore:InvokeAgentRuntime" not in actions("PublisherRole")
    assert r["Gateway"]["Properties"]["AuthorizerType"] == "AWS_IAM"
    assert "AuthorizerConfiguration" not in r["Runtime"]["Properties"]
