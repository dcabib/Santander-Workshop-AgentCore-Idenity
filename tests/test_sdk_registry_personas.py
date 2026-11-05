"""Separação IAM e recusa de alterações inesperadas nas personas."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from scripts.sdk_notebook_lessons import build_cleanup, build_registry_personas
from tests.test_sdk_gateway import ACCOUNT, REGION
from tests.test_sdk_registry import RegistryAWS, run_registry


class PersonaAWS(RegistryAWS):
    def __init__(self):
        super().__init__()
        self.extra_attached = []
        self.active_persona = None
        self.persona_calls = []
        self.objects["roles"]["Participant"] = {
            "Arn": f"arn:aws:iam::{ACCOUNT}:role/event/Participant",
        }

    def session(self, **args):
        if not args.get("aws_access_key_id"):
            return self
        owner = self
        name = args["aws_access_key_id"]

        def client(service):
            base = owner.client(service)

            class Client:
                exceptions = base.exceptions

                def __getattr__(self, method):
                    def call(**kwargs):
                        previous = owner.active_persona
                        owner.active_persona = name
                        owner.persona_calls.append((name, method))
                        try:
                            return getattr(base, method)(**kwargs)
                        finally:
                            owner.active_persona = previous
                    return call
            return Client()
        return SimpleNamespace(client=client)

    def respond(self, service, method, args):
        if method == "assume_role":
            name = {
                "admin_persona": "approver", "publisher_persona": "publisher",
                "consumer_persona": "consumer",
            }[args["RoleArn"].rsplit("/", 1)[1]]
            return {
                "Credentials": {"AccessKeyId": name, "SecretAccessKey": "test", "SessionToken": "test"},
                "AssumedRoleUser": {"Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/{name}/test"},
                "ResponseMetadata": {"RequestId": "assume-request"},
            }
        if method == "get_caller_identity":
            return {
                "Account": ACCOUNT, "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/Participant/session",
                "ResponseMetadata": {"RequestId": "sts-test"},
            }
        if method == "get_agent_runtime":
            if self.active_persona in {"approver", "publisher"}:
                raise ClientError({
                    "Error": {"Code": "AccessDeniedException", "Message": "Not allowed"},
                    "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "deny-runtime"},
                }, method)
            return {**self.objects["runtime"], "ResponseMetadata": {"RequestId": "runtime-read"}}
        if method == "list_tags_for_resource" and service == "bedrock-agentcore-control":
            return {"tags": self.objects["runtime"]["tags"]}
        if method == "list_attached_role_policies":
            return {"AttachedPolicies": self.extra_attached}
        if method == "list_role_policies":
            return {
                "PolicyNames": [name for role, name in self.objects["role_policies"] if role == args["RoleName"]],
            }
        if method == "delete_role_policy":
            del self.objects["role_policies"][args["RoleName"], args["PolicyName"]]
            return {}
        if method == "delete_role":
            del self.objects["roles"][args["RoleName"]]
            return {}
        if method == "get_role" and args["RoleName"] not in self.objects["roles"]:
            raise self.clients["iam"].exceptions.NoSuchEntityException(
                {"Error": {"Code": "NoSuchEntity", "Message": "Not found"}}, method,
            )
        return super().respond(service, method, args)


def run_personas(aws):
    namespace = {}
    with patch("boto3.Session", side_effect=aws.session), patch("time.sleep"):
        for cell in build_registry_personas().cells:
            if cell.cell_type == "code":
                exec(cell.source, namespace)
    return namespace


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='personas-test'\n")
    monkeypatch.chdir(tmp_path)
    aws = PersonaAWS()
    namespace = run_registry(aws)
    arn = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:runtime/test-abcdefghij"
    aws.objects["runtime"] = {
        "agentRuntimeArn": arn, "agentRuntimeId": "test-abcdefghij",
        "status": "READY", "tags": namespace["state"].tags,
    }
    namespace["state"].record("runtime.instance", {"arn": arn, "id": "test-abcdefghij"}, lesson="03")
    return aws


def test_personas_limit_actions_and_trust_and_resume_without_mutations(workspace):
    namespace = run_personas(workspace)
    assert not any(method == "simulate_principal_policy" for _, method, _ in workspace.calls)
    assert set(workspace.persona_calls) == {
        (name, method) for name in ("publisher", "approver", "consumer")
        for method in ("get_registry", "get_agent_runtime")
    }
    assert {entry["name"] for entry in namespace["persona_entries"].values()} == {
        "admin_persona", "publisher_persona", "consumer_persona",
    }
    principal = namespace["TRUST"]["Statement"][0]["Principal"]["AWS"]
    assert principal == f"arn:aws:iam::{ACCOUNT}:role/event/Participant"
    assert all(
        "*" not in action
        for policy in namespace["PERSONA_POLICIES"].values()
        for statement in policy["Statement"]
        for action in statement["Action"]
    )
    count = len(workspace.calls)
    resumed = run_personas(workspace)
    assert resumed["persona_entries"] == namespace["persona_entries"]
    assert not any(method.startswith(("put_", "update_", "create_")) for _, method, _ in workspace.calls[count:])


@pytest.mark.parametrize("drift", ["policy", "trust", "attached", "boundary"])
def test_persona_drift_is_never_reconciled_silently(workspace, drift):
    namespace = run_personas(workspace)
    entry = namespace["persona_entries"]["approver"]
    role = workspace.objects["roles"][entry["name"]]
    if drift == "policy":
        workspace.objects["role_policies"][entry["name"], "Lesson07Persona"]["Statement"][0]["Resource"] = "*"
    elif drift == "trust":
        role["AssumeRolePolicyDocument"]["Statement"][0]["Principal"]["AWS"] = f"arn:aws:iam::{ACCOUNT}:root"
    elif drift == "attached":
        workspace.extra_attached = [{"PolicyName": "Unexpected", "PolicyArn": "arn:aws:iam::aws:policy/ReadOnlyAccess"}]
    else:
        role["PermissionsBoundary"] = {"PermissionsBoundaryArn": "unexpected"}
    count = len(workspace.calls)
    with pytest.raises(AssertionError):
        run_personas(workspace)
    assert not any(method.startswith(("put_", "update_", "create_")) for _, method, _ in workspace.calls[count:])

def test_existing_official_persona_is_not_adopted_or_overwritten(workspace):
    workspace.objects["roles"]["consumer_persona"] = {"Arn": "another-workshop"}
    count = len(workspace.calls)
    with pytest.raises(RuntimeError, match="PERSONA_NAME_ALREADY_IN_USE"):
        run_personas(workspace)
    assert not any(method.startswith(("put_", "update_", "create_")) for _, method, _ in workspace.calls[count:])


def test_cleanup_removes_persona_roles_and_keeps_participant(workspace):
    namespace = run_personas(workspace)
    state = namespace["state"]
    # Esta fixture representa somente o catálogo/personas; o Runtime é dependência externa ao teste.
    state.forget("runtime.instance", expected=state.get("runtime.instance"))
    cells = build_cleanup().cells
    exec(next(c.source for c in cells if c.cell_type == "code" and "supported =" in c.source), namespace)
    exec(next(c.source for c in cells if c.cell_type == "code" and 'for persona in ("developer"' in c.source and "iam.delete_role(" in c.source), namespace)
    assert set(workspace.objects["roles"]) == {"Participant"}
    assert not any(key.startswith("registry.role.") for key in state.data["resources"])
