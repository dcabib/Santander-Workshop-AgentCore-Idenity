import json
import zipfile
from unittest.mock import Mock

import pytest

from infra.workshop.generate import runner
from santander_demo.aws_endpoints import gateway_region
from santander_demo.aws_workshop.config import DOMAINS, validate
from santander_demo.aws_workshop.manifest import (
    account_plan,
    assert_account_plan,
    selected_labs,
)
from santander_demo.aws_workshop.runtime_boundary import policy
from santander_demo.registry_workflow.contracts import bundle
from scripts import workshop_runner


@pytest.fixture
def config():
    return {
        "schema_version": 1, "project": "santander-workshop", "topology": "single-account",
        "region": "us-west-2", "auth_provider": "cognito",
        "source_kind": "aws_simulated_databricks",
        "accounts": {domain: {"id": "111111111111" if domain == "platform" else None,
                              "profile": None} for domain in DOMAINS},
    }


def test_single_account_explicit_topology_selects_twelve_labs(config):
    validate(config)
    assert selected_labs(config) == [f"{n:02d}" for n in [*range(10), 15, 16]]
    report = account_plan(config, runner=True)
    assert report["status"] == "ACCOUNTS_CONFIGURED"
    assert report["runner_required_accounts"] == ["platform"]


@pytest.mark.parametrize("lab", ["10", "11", "12", "13", "14"])
def test_single_account_never_promotes_multicount_lab(config, lab):
    report = account_plan(config, [lab], runner=True)
    assert report["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="single-account"):
        assert_account_plan(report)


@pytest.mark.parametrize("field,value", [
    ("region", "eu-west-3"), ("topology", "automatic"),
])
def test_unimplemented_regions_and_implicit_topologies_are_rejected(config, field, value):
    config[field] = value
    with pytest.raises(ValueError):
        validate(config)


def test_single_account_cannot_hide_additional_account_ids(config):
    config["accounts"]["retail-banking"]["id"] = "222222222222"
    with pytest.raises(ValueError, match="SINGLE_ACCOUNT_DOMAINS_MUST_BE_EMPTY"):
        validate(config)


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_registry_descriptors_bind_gateway_and_runtime_to_same_region(region):
    gateway = f"https://test.gateway.bedrock-agentcore.{region}.amazonaws.com/mcp"
    runtime = f"arn:aws:bedrock-agentcore:{region}:111111111111:runtime/test"
    assert gateway_region(gateway) == region
    assert bundle(gateway, runtime)["AGENT"]["recordType"] == "AGENT"
    other = "us-east-1" if region == "us-west-2" else "us-west-2"
    with pytest.raises(ValueError, match="RUNTIME_INVALID"):
        bundle(gateway, runtime.replace(region, other))


def test_registry_endpoint_validation_rejects_credential_redirect():
    with pytest.raises(ValueError, match="GATEWAY_INVALID"):
        gateway_region("https://test.gateway.bedrock-agentcore.us-west-2.amazonaws.com.evil.test/mcp")


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_regional_runtime_boundary_preserves_exact_gateway_role(region):
    runtime = f"arn:aws:bedrock-agentcore:{region}:111111111111:runtime/test"
    role = "arn:aws:iam::111111111111:role/gateway"
    statements = policy(runtime, role)["Statement"]
    assert statements[0]["Principal"] == {"AWS": role}
    assert statements[1]["Condition"] == {"ArnNotEquals": {"aws:PrincipalArn": role}}
    assert all(statement["Resource"] == runtime for statement in statements)
    with pytest.raises(ValueError, match="SAME_ACCOUNT"):
        policy(runtime, role.replace("111111111111", "222222222222"))


def test_runner_cannot_expand_labs_without_updating_iac(config, monkeypatch):
    cb = Mock()
    cb.batch_get_projects.return_value = {"projects": [{
        "environment": {"environmentVariables": [{"name": "WORKSHOP_LABS", "value": "00 01"}]},
    }]}
    check = Mock()
    monkeypatch.setattr(workshop_runner, "check_selection", check)
    with pytest.raises(ValueError, match="RUNNER_REDEPLOY_REQUIRED"):
        workshop_runner.preflight_run(config, cb, "project", ["09"])
    check.assert_not_called()
    cb.start_build.assert_not_called()


def test_core_only_package_needs_no_integration_outputs_or_foreign_roles(config, tmp_path, monkeypatch):
    monkeypatch.setattr(workshop_runner, "ROOT", tmp_path)
    for name in ["pyproject.toml", "uv.lock", "README.md"]:
        (tmp_path / name).write_text("placeholder")
    archive, _ = workshop_runner.package(config, ["00", "01"])
    with zipfile.ZipFile(archive) as zipped:
        packaged = json.loads(zipped.read("config/aws.workshop.json"))
        assert not any("role_arn" in account for account in packaged["accounts"].values())
        assert set(zipped.namelist()) == {
            "pyproject.toml", "uv.lock", "README.md", "config/aws.workshop.json",
        }


def test_core_runner_omits_unused_integrations_and_sts_grants(config, tmp_path, monkeypatch):
    monkeypatch.setattr(workshop_runner, "ROOT", tmp_path)
    envs = {
        "identity": {"SupervisorSecretArn": "arn:aws:secretsmanager:us-west-2:111111111111:secret:login"},
        "gateway": {"GatewayRoleArn": "arn:aws:iam::111111111111:role/gateway",
                    "GatewayArn": "arn:aws:bedrock-agentcore:us-west-2:111111111111:gateway/test"},
        "backend": {"RuntimeArn": "arn:aws:bedrock-agentcore:us-west-2:111111111111:runtime/test"},
        "bootstrap": {"ArtifactBucket": "owned-artifacts"},
    }
    monkeypatch.setattr(workshop_runner, "outputs", lambda _, phase: envs[phase])
    monkeypatch.setattr(workshop_runner, "session", Mock())
    params = workshop_runner.parameters(config, "source/test.zip", ["00", "01"])
    assert params["AssumeRoleArns"] == params["PersonaArns"] == params["TerraformPoolArn"] == ""
    assert params["KnowledgeArns"] == params["SourceArns"] == ""
    assert params["Labs"] == "00 01"
    assert "None" not in json.dumps(params)


def test_optional_iam_statements_disappear_instead_of_granting_wildcards():
    template = runner()
    statements = template["Resources"]["Role"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    optional = [s["Fn::If"] for s in statements if "Fn::If" in s]
    assert {condition for condition, _, _ in optional} == {
        "HasAssumeRoleArns", "HasPersonaArns", "HasTerraformPoolArn", "HasKnowledgeArns", "HasSourceArns",
    }
    for condition, statement, absent in optional:
        assert condition in template["Conditions"]
        assert statement["Resource"] != "*"
        assert absent == {"Ref": "AWS::NoValue"}


@pytest.mark.parametrize("field,wrong", [("account", "222222222222"), ("region", "us-east-1")])
def test_packaging_rejects_integration_from_reference_environment(
    config, tmp_path, monkeypatch, field, wrong,
):
    monkeypatch.setattr(workshop_runner, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    registry = {"account": "111111111111", "region": "us-west-2", field: wrong}
    (tmp_path / "config/aws.registry.json").write_text(json.dumps(registry))
    config["integrations"] = {"registry": {"config": "config/aws.registry.json"}}
    with pytest.raises(ValueError, match="RUNNER_INTEGRATION_ACCOUNT_REGION_MISMATCH"):
        workshop_runner.integration_configs(config, ["06"])
