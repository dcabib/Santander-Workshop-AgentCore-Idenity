"""A geração nunca promove o rascunho nem ignora findings ou contraexemplos."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.sdk_notebook_lessons import build_cleanup, build_policy_authoring
from tests.test_sdk_gateway import provisioning_cells
from tests.test_sdk_policy import PolicyAWS, policy_setup


class AuthoringAWS(PolicyAWS):
    def __init__(self):
        super().__init__()
        self.policies = {}
        self.findings = []
        self.statement_override = None
        self.definition_type = "policy"

    def respond(self, service, method, args):
        if method == "create_policy":
            value = super().respond(service, method, args)
            policy_id = "policy-" + str(len(self.policies) + 1).zfill(10)
            value["policyId"] = policy_id
            value["policyArn"] = self.objects["engine"]["policyEngineArn"] + "/policy/" + policy_id
            self.policies[policy_id] = deepcopy(value)
            return value
        if method == "get_policy":
            if args["policyId"] not in self.policies:
                self.not_found(method)
            return self.policies[args["policyId"]]
        if method == "list_policies":
            return {"policies": list(self.policies.values())}
        if method == "delete_policy":
            del self.policies[args["policyId"]]
            return {}
        if method == "delete_policy_engine":
            assert not self.policies
            self.objects.pop("policy", None)
            return super().respond(service, method, args)
        if method == "start_policy_generation":
            self.objects["generation"] = {
                **args, "policyGenerationId": "generation-abcdefghij",
                "policyGenerationArn": self.objects["engine"]["policyEngineArn"] + "/policy-generation/generation-abcdefghij",
                "status": "GENERATED", "statusReasons": [],
            }
            return self.objects["generation"]
        if method == "get_policy_generation":
            return self.objects["generation"]
        if method == "list_policy_generations":
            return {"policyGenerations": [self.objects["generation"]]}
        if method == "list_policy_generation_assets":
            statement = self.statement_override or next(iter(self.policies.values()))["definition"]["cedar"]["statement"]
            return {"policyGenerationAssets": [{
                "policyGenerationAssetId": "asset-abcdefghij", "rawTextFragment": "synthetic intent",
                "definition": {self.definition_type: {"statement": statement}}, "findings": self.findings,
            }]}
        return super().respond(service, method, args)


@pytest.fixture
def authoring_workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='authoring-test'\n")
    monkeypatch.chdir(tmp_path)
    aws = AuthoringAWS()
    namespace = {}
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    with (
        patch("boto3.Session", return_value=aws),
        patch("httpx.post", return_value=denied), patch("time.sleep"),
    ):
        for source in provisioning_cells():
            exec(source, namespace)
    policy_setup(aws)
    return aws


def authoring_setup(aws):
    namespace = {}
    with patch("boto3.Session", return_value=aws), patch("time.sleep"):
        for cell in build_policy_authoring().cells:
            if cell.cell_type != "code":
                continue
            if "jwks = jwt.PyJWKClient" in cell.source:
                break
            exec(cell.source, namespace)
    return namespace


@pytest.mark.parametrize("definition_type", ["cedar", "policy"])
def test_generation_creates_only_log_only_policy_and_resumes(authoring_workspace, definition_type):
    aws = authoring_workspace
    aws.definition_type = definition_type
    active_before = deepcopy(next(iter(aws.policies.values())))
    count = len(aws.calls)
    namespace = authoring_setup(aws)
    mutations = [(method, args) for _, method, args in aws.calls[count:] if method.startswith(("create_", "update_", "put_", "start_"))]
    assert [method for method, _ in mutations] == ["start_policy_generation", "create_policy"]
    assert mutations[1][1]["enforcementMode"] == "LOG_ONLY"
    assert mutations[1][1]["validationMode"] == "FAIL_ON_ANY_FINDINGS"
    assert next(iter(aws.policies.values())) == active_before
    assert aws.objects["gateway"]["policyEngineConfiguration"]["mode"] == "ENFORCE"
    count = len(aws.calls)
    resumed = authoring_setup(aws)
    assert resumed["draft_entry"] == namespace["draft_entry"]
    assert not [
        method for _, method, _ in aws.calls[count:]
        if method.startswith(("create_", "update_", "put_", "start_"))
    ]


@pytest.mark.parametrize("finding_type", ["WARNING", "INVALID"])
def test_findings_prevent_policy_creation(authoring_workspace, finding_type):
    aws = authoring_workspace
    aws.findings = [{"type": finding_type, "description": "Review needed"}]
    count = len(aws.calls)
    with pytest.raises(AssertionError, match="policy generation findings"):
        authoring_setup(aws)
    assert not [method for _, method, _ in aws.calls[count:] if method == "create_policy"]


def test_overbroad_generated_policy_is_rejected(authoring_workspace):
    aws = authoring_workspace
    aws.statement_override = "permit(principal, action, resource);"
    count = len(aws.calls)
    with pytest.raises(AssertionError, match="GENERATED_POLICY_INTENT_MISMATCH"):
        authoring_setup(aws)
    assert not [method for _, method, _ in aws.calls[count:] if method == "create_policy"]


def test_unknown_definition_type_is_not_reinterpreted_as_cedar(authoring_workspace):
    aws = authoring_workspace
    aws.definition_type = "policyGeneration"
    count = len(aws.calls)
    with pytest.raises(AssertionError, match="single policy statement"):
        authoring_setup(aws)
    assert not [method for _, method, _ in aws.calls[count:] if method == "create_policy"]


def test_non_cedar_extension_cannot_be_created_as_cedar(authoring_workspace):
    aws = authoring_workspace
    aws.statement_override = "this is not a Cedar policy"
    count = len(aws.calls)
    with pytest.raises(ValueError):
        authoring_setup(aws)
    assert not [method for _, method, _ in aws.calls[count:] if method == "create_policy"]


def test_cleanup_verifies_both_policies_and_removes_them_before_engine(authoring_workspace):
    aws = authoring_workspace
    namespace = authoring_setup(aws)
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    exec(check, namespace)
    state = namespace["state"]
    state.forget("gateway.instance", expected=state.get("gateway.instance"))
    del aws.objects["gateway"]
    delete = next(
        c.source for c in build_cleanup().cells
        if c.cell_type == "code" and "control.delete_policy_engine(" in c.source
    )
    exec(delete, namespace)
    assert not aws.policies
    assert state.get("policy.generation") is None
    assert state.get("policy.draft") is None and state.get("policy.engine") is None


def test_cleanup_rejects_unknown_policy_before_any_delete(authoring_workspace):
    aws = authoring_workspace
    namespace = authoring_setup(aws)
    foreign = deepcopy(next(iter(aws.policies.values())))
    foreign["policyId"] = "foreign-policy"
    aws.policies["foreign-policy"] = foreign
    check = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    count = len(aws.calls)
    with pytest.raises(AssertionError, match="UNREGISTERED_ENGINE_POLICIES"):
        exec(check, namespace)
    assert not [method for _, method, _ in aws.calls[count:] if method.startswith("delete_")]
