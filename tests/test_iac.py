import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parents[1]


def load_provider():
    spec = importlib.util.spec_from_file_location(
        "registry_handler", ROOT / "infra/providers/registry_handler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_registry_sdk_contract_and_idempotency():
    module = load_provider()
    client = boto3.client(
        "bedrock-agentcore-control",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    event = {
        "StackId": "stack",
        "LogicalResourceId": "Catalog",
        "RequestType": "Create",
        "ResourceProperties": {"Kind": "Registry", "Name": "demo"},
    }
    token = module.stable_token(event)
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:registry/demo-1234567890"
    with Stubber(client) as stub:
        stub.add_response(
            "create_registry",
            {"registryArn": arn},
            {
                "name": "demo-" + token[:10],
                "description": "Catálogo sintético Santander; governado pelo CloudFormation",
                "authorizerType": "AWS_IAM",
                "approvalConfiguration": {"autoApproval": False},
                "clientToken": token,
            },
        )
        # GetRegistry requires metadata; exercised separately with a small fake below.
        provider = module.Provider(client)
        provider.wait = lambda *a, **kw: {"status": "READY"}
        physical, data = provider.handle(event)
        assert physical == arn and data["Id"] == "demo-1234567890"
        assert module.stable_token({**event, "RequestType": "Update"}) == token
        stub.assert_no_pending_responses()


def test_registry_delete_is_idempotent_and_does_not_delete_other_records():
    module = load_provider()
    client = boto3.client(
        "bedrock-agentcore-control",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:registry/reg123/record/record123"
    with Stubber(client) as stub:
        stub.add_client_error(
            "delete_registry_record",
            "ResourceNotFoundException",
            expected_params={"registryId": "reg123", "recordId": "record123"},
        )
        module.Provider(client).delete("Record", arn)
        stub.assert_no_pending_responses()


def test_approval_retry_does_not_repeat_transition_or_reverse_decision():
    module = load_provider()

    class Client:
        calls = 0

        def get_registry_record(self, **kw):
            return {"status": "APPROVED"}

        def update_registry_record_status(self, **kw):
            self.calls += 1

    client = Client()
    event = {
        "StackId": "stack",
        "LogicalResourceId": "Approval",
        "RequestType": "Create",
        "ResourceProperties": {
            "Kind": "Approval",
            "RegistryId": "reg",
            "RecordId": "record",
            "Decision": "APPROVED",
        },
    }
    provider = module.Provider(client)
    provider.handle(event)
    assert client.calls == 0
    event["ResourceProperties"]["Decision"] = "REJECTED"
    with pytest.raises(ValueError, match="NEW_RECORD_VERSION_REQUIRED"):
        provider.handle(event)


def test_registry_wait_is_bounded():
    module = load_provider()

    class Client:
        def get_registry(self, **kw):
            return {"status": "CREATING"}

    with pytest.raises(TimeoutError):
        module.Provider(Client(), sleep=lambda _: None, max_polls=2).wait(
            "get_registry", {"registryId": "reg"}, {"READY"}
        )


def test_templates_preserve_security_boundaries():
    hub = json.loads((ROOT / "infra/templates/hub.json").read_text())
    resources = hub["Resources"]
    assert resources["Gateway"]["Properties"]["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
    assert resources["Gateway"]["Properties"]["AuthorizerType"] == "CUSTOM_JWT"
    for resource in resources.values():
        if resource["Type"] == "AWS::BedrockAgentCore::Policy":
            assert resource["Properties"]["ValidationMode"] == "FAIL_ON_ANY_FINDINGS"
    catalog = json.loads((ROOT / "infra/templates/registry.json").read_text())
    publisher = json.dumps(catalog["Resources"]["RecordProviderRole"])
    approver = json.dumps(catalog["Resources"]["ApprovalProviderRole"])
    assert "UpdateRegistryRecordStatus" not in publisher
    assert "CreateRegistryRecord" not in approver
    all_text = json.dumps([hub, catalog])
    assert "AWS::IAM::AccessKey" not in all_text
    assert "IGNORE_ALL_FINDINGS" not in all_text


def test_record_lifecycle_uses_valid_sdk_parameters():
    import botocore.session
    from botocore.validate import validate_parameters

    model = botocore.session.get_session().get_service_model("bedrock-agentcore-control")
    module = load_provider()
    arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:registry/reg123/record/record123"

    class Client:
        status = "DRAFT"

        def create_registry_record(self, **kwargs):
            validate_parameters(kwargs, model.operation_model("CreateRegistryRecord").input_shape)
            return {"recordArn": arn}

        def get_registry_record(self, **kwargs):
            validate_parameters(kwargs, model.operation_model("GetRegistryRecord").input_shape)
            return {"status": self.status}

        def submit_registry_record_for_approval(self, **kwargs):
            validate_parameters(
                kwargs, model.operation_model("SubmitRegistryRecordForApproval").input_shape
            )
            self.status = "PENDING_APPROVAL"

    event = {
        "StackId": "stack",
        "LogicalResourceId": "Record",
        "RequestType": "Create",
        "ResourceProperties": {
            "Kind": "Record",
            "RegistryId": "reg123",
            "Name": "synthetic",
            "Description": "synthetic",
            "Version": "1.0",
            "Submit": "true",
            "Descriptors": {
                "mcp": {
                    "server": {"schemaVersion": "2025-12-11", "inlineContent": "{}"},
                    "tools": {"protocolVersion": "2025-11-25", "inlineContent": "{}"},
                }
            },
        },
    }
    client = Client()
    physical, data = module.Provider(client).handle(event)
    assert physical == arn and data["Id"] == "record123"
    assert client.status == "PENDING_APPROVAL"
    assert module.stable_token(event) != module.stable_token(
        {
            **event,
            "ResourceProperties": {**event["ResourceProperties"], "Version": "2.0"},
        }
    )


def test_policy_draft_contract_never_publishes(monkeypatch):
    import sys

    import botocore.session
    from botocore.validate import validate_parameters

    monkeypatch.setitem(sys.modules, "registry_handler", load_provider())
    spec = importlib.util.spec_from_file_location(
        "policy_draft_handler", ROOT / "infra/providers/policy_draft_handler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = botocore.session.get_session().get_service_model("bedrock-agentcore-control")

    class Client:
        def start_policy_generation(self, **kwargs):
            validate_parameters(kwargs, model.operation_model("StartPolicyGeneration").input_shape)
            assert kwargs["content"]["rawText"] == "Somente Riscos pode consultar até 50 registros."
            return {"policyGenerationId": "generation123"}

        def get_policy_generation(self, **kwargs):
            return {
                "status": "GENERATED",
                "policyGenerationId": "generation123",
                "policyGenerationArn": "arn:policy-draft",
            }

        def create_policy(self, **kwargs):
            raise AssertionError("Rascunhos não podem publicar políticas")

    event = {
        "RequestType": "Create",
        "StackId": "stack",
        "LogicalResourceId": "Draft",
        "ResourceProperties": {
            "PolicyEngineId": "engine1234567890",
            "GatewayArn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:gateway/gateway123",
            "RawText": "Somente Riscos pode consultar até 50 registros.",
        },
    }
    _, data = module.generate(Client(), event)
    assert data["ReviewRequired"] == "true"
