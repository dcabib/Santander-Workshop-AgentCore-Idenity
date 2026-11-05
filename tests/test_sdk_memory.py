"""Contratos Memory/DynamoDB, revogação persistente e limpeza restrita."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError

from scripts.sdk_notebook_lessons import build_cleanup, build_memory
from tests.test_sdk_gateway import ACCOUNT, REGION, provisioning_cells
from tests.test_sdk_registry_personas import PersonaAWS


class MemoryAWS(PersonaAWS):
    def __init__(self):
        super().__init__()
        model = boto3.Session(
            region_name=REGION, aws_access_key_id="model", aws_secret_access_key="model",
        )
        for service in ("dynamodb", "cognito-identity"):
            self.clients[service] = model.client(service)
        self.rows = {}
        self.events = []
        self.actor = None
        self.denials = []

    def wrapped(self, service, person=None):
        base = super().client(service)
        owner = self

        class Client:
            exceptions = base.exceptions
            meta = base.meta

            def get_waiter(self, name):
                return base.get_waiter(name)

            def __getattr__(self, method):
                def call(**args):
                    owner.actor = person
                    return getattr(base, method)(**args)
                return call

        return Client()

    def client(self, service, **kwargs):
        return self.wrapped(service)

    def session(self, **args):
        person = args.get("aws_access_key_id")
        if person:
            return SimpleNamespace(client=lambda service: self.wrapped(service, person))
        return self

    def deny(self, method):
        self.denials.append((self.actor, method))
        raise ClientError({
            "Error": {"Code": "AccessDeniedException", "Message": "Contract authorization denial"},
            "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "denial-request"},
        }, method)

    def response(self, **values):
        return {**values, "ResponseMetadata": {"RequestId": "memory-test-request"}}

    def key(self, item):
        return item["PK"]["S"], item["SK"]["S"]

    def respond(self, service, method, args):
        if method == "initiate_auth":
            return {"AuthenticationResult": {"IdToken": args["AuthParameters"]["USERNAME"]}}
        if method == "create_identity_pool":
            self.objects["identity_pool"] = {**args, "IdentityPoolId": REGION + ":00000000-0000-0000-0000-000000000001"}
            self.objects["identity_mapping"] = {"Roles": {}, "RoleMappings": {}}
            return self.response(**self.objects["identity_pool"])
        if method == "describe_identity_pool":
            if "identity_pool" not in self.objects:
                raise self.clients[service].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return self.response(**self.objects["identity_pool"])
        if method == "get_identity_pool_roles":
            return self.response(IdentityPoolId=args["IdentityPoolId"], **self.objects["identity_mapping"])
        if method == "set_identity_pool_roles":
            self.objects["identity_mapping"] = {key: args[key] for key in ("Roles", "RoleMappings")}
            return {}
        if method == "get_id":
            if not args.get("Logins"):
                raise ClientError({
                    "Error": {"Code": "NotAuthorizedException", "Message": "Anonymous forbidden"},
                    "ResponseMetadata": {"HTTPStatusCode": 400, "RequestId": "anonymous-denied"},
                }, method)
            person = next(iter(args["Logins"].values()))
            suffix = "1" if person == "analista" else "2"
            return self.response(IdentityId=REGION + ":00000000-0000-0000-0000-00000000000" + suffix)
        if method == "get_credentials_for_identity":
            person = next(iter(args["Logins"].values()))
            mapping = next(iter(self.objects["identity_mapping"]["RoleMappings"].values()))
            assert mapping["AmbiguousRoleResolution"] == "Deny"
            matches = [rule for rule in mapping["RulesConfiguration"]["Rules"] if rule["Value"] == person + "-subject"]
            assert len(matches) == 1 and matches[0]["RoleARN"].endswith("-memory-" + person)
            return self.response(
                IdentityId=args["IdentityId"],
                Credentials={"AccessKeyId": person, "SecretKey": "test", "SessionToken": "test"},
            )
        if method == "delete_identity_pool":
            del self.objects["identity_pool"], self.objects["identity_mapping"]
            return {}
        if method == "create_memory":
            self.objects["memory"] = {
                **args, "id": "santander_memory-abcdefghij",
                "arn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:memory/santander_memory-abcdefghij",
                "status": "ACTIVE", "strategies": [],
            }
            return self.response(memory=self.objects["memory"])
        if method == "get_memory":
            if "memory" not in self.objects:
                raise self.clients[service].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return self.response(memory=self.objects["memory"])
        if method == "list_tags_for_resource" and args["resourceArn"] == self.objects.get("memory", {}).get("arn"):
            return {"tags": self.objects["memory"]["tags"]}
        if method == "list_tags_for_resource" and args["resourceArn"] == self.objects.get("gateway", {}).get("gatewayArn"):
            return {"tags": self.objects["gateway"]["tags"]}
        if method == "create_table":
            self.objects["table"] = {
                **args, "TableArn": f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{args['TableName']}",
                "TableId": "11111111-1111-1111-1111-111111111111",
                "TableStatus": "ACTIVE", "BillingModeSummary": {"BillingMode": args["BillingMode"]},
            }
            return {"TableDescription": self.objects["table"]}
        if method == "describe_table":
            if "table" not in self.objects:
                raise self.clients[service].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return {"Table": self.objects["table"]}
        if method == "list_tags_of_resource":
            return {"Tags": self.objects["table"]["Tags"]}
        if method == "put_item":
            assert args["ConditionExpression"] == "attribute_not_exists(PK) AND attribute_not_exists(SK)"
            assert self.key(args["Item"]) not in self.rows
            self.rows[self.key(args["Item"])] = args["Item"]
            return {}
        if method == "get_item":
            if self.actor:
                role = next(role for role in self.objects["roles"] if role.endswith("-memory-" + self.actor))
                policy = self.objects["role_policies"][role, "Lesson15ActorAndSource"]
                allowed = policy["Statement"][1]["Condition"]["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"]
                if args["Key"]["PK"]["S"] not in allowed:
                    self.deny(method)
            item = self.rows.get(self.key(args["Key"]))
            return self.response(**({"Item": item} if item else {}))
        if method == "delete_item":
            assert self.actor is None
            assert args["ConditionExpression"] == "workshop_run = :run"
            item = self.rows.pop(self.key(args["Key"]))
            assert item["workshop_run"] == args["ExpressionAttributeValues"][":run"]
            return self.response(Attributes=item)
        if method == "scan":
            return {"Items": list(self.rows.values())}
        if method in {"create_event", "list_events"}:
            if self.actor:
                role = next(role for role in self.objects["roles"] if role.endswith("-memory-" + self.actor))
                policy = self.objects["role_policies"][role, "Lesson15ActorAndSource"]
                actor_id = policy["Statement"][0]["Condition"]["StringEquals"]["bedrock-agentcore:actorId"]
                if args["actorId"] != actor_id:
                    self.deny(method)
            if method == "create_event":
                assert not self.events
                self.events.append({**args, "eventId": "event-abcdefghij"})
                return self.response(event=self.events[0])
            return self.response(events=self.events)
        if method == "list_actors":
            return {"actorSummaries": [{"actorId": event["actorId"]} for event in self.events]}
        if method == "list_sessions":
            return {"sessionSummaries": [{"actorId": event["actorId"], "sessionId": event["sessionId"]} for event in self.events]}
        if method == "delete_event":
            self.events = []
            return {"eventId": args["eventId"]}
        if method == "get_event":
            if not self.events:
                raise self.clients[service].exceptions.ResourceNotFoundException(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}}, method,
                )
            return {"event": self.events[0]}
        if method == "delete_memory":
            assert not self.events
            del self.objects["memory"]
            return {"memoryId": args["memoryId"]}
        if method == "delete_table":
            del self.objects["table"]
            self.rows.clear()
            return {}
        return super().respond(service, method, args)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='memory-test'\n")
    monkeypatch.chdir(tmp_path)
    aws = MemoryAWS()
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "denial-request"})
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied), patch("time.sleep"):
        namespace = {}
        for source in provisioning_cells():
            exec(source, namespace)
    return aws


def run_memory(aws):
    namespace = {}

    def decode(token, key, **args):
        return {"iss": args["issuer"], "aud": args["audience"], "sub": token + "-subject", "token_use": "id"}

    with (
        patch("boto3.Session", side_effect=aws.session), patch("time.sleep"),
        patch("jwt.PyJWKClient", return_value=SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key="test"))),
        patch("jwt.decode", side_effect=decode),
    ):
        for cell in build_memory().cells:
            if cell.cell_type == "code":
                exec(cell.source, namespace)
    return namespace


def test_memory_reference_does_not_restore_revoked_view_and_resume_preserves_revocation(workspace):
    namespace = run_memory(workspace)
    assert len(workspace.events) == 1 and len(workspace.rows) == 2
    assert workspace.denials == [("auditor", "list_events"), ("analista", "get_item")]
    assert namespace["state"].get("memory.source_item.analista") is None
    assert all("Tags" not in args for _, method, args in workspace.calls if method == "create_table")
    assert not any(method == "assume_role" for _, method, _ in workspace.calls)
    assert namespace["login_tokens"] == {}
    assert workspace.objects["identity_pool"]["AllowUnauthenticatedIdentities"] is False
    assert workspace.objects["identity_pool"]["AllowClassicFlow"] is False
    for entry in namespace["memory_roles"].values():
        trust = workspace.objects["roles"][entry["name"]]["AssumeRolePolicyDocument"]["Statement"][0]
        assert trust["Principal"] == {"Federated": "cognito-identity.amazonaws.com"}
        assert trust["Condition"]["StringEquals"]["cognito-identity.amazonaws.com:aud"] == namespace["identity_pool"]["id"]
    payload = json.dumps(workspace.events[0]["payload"])
    assert namespace["CONTENT"] not in payload and namespace["DOCUMENT_ID"] in payload
    count = len(workspace.calls)
    run_memory(workspace)
    assert len(workspace.rows) == 2
    assert not any(method.startswith(("put_", "create_", "delete_")) for _, method, _ in workspace.calls[count:])


@pytest.mark.parametrize("drift", ["source", "role", "event", "federation", "mapping", "replaced_table"])
def test_memory_cleanup_refuses_drift_before_any_delete(workspace, drift):
    namespace = run_memory(workspace)
    state = namespace["state"]
    # Isola os recursos da aula 15; a fixture 01 apenas fornece identidades.
    for key in list(state.data["resources"]):
        if not key.startswith("memory."):
            state.forget(key, expected=state.get(key))
    if drift == "source":
        workspace.rows["UNEXPECTED", "CONTENT"] = {"PK": {"S": "UNEXPECTED"}, "SK": {"S": "CONTENT"}}
    elif drift == "role":
        entry = state.get("memory.role.analista")
        workspace.objects["role_policies"][entry["name"], entry["policy_name"]]["Statement"][0]["Resource"] = "*"
    elif drift == "event":
        workspace.events[0]["payload"] = [{"conversational": {"role": "USER", "content": {"text": "changed"}}}]
    elif drift == "federation":
        workspace.objects["identity_pool"]["AllowUnauthenticatedIdentities"] = True
    elif drift == "mapping":
        workspace.objects["identity_mapping"]["Roles"] = {"authenticated": "unexpected"}
    else:
        workspace.objects["table"]["TableId"] = "22222222-2222-2222-2222-222222222222"
    count = len(workspace.calls)
    source = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    with pytest.raises(AssertionError):
        exec(source, namespace)
    assert not any(method.startswith("delete_") for _, method, _ in workspace.calls[count:])

def test_memory_resume_rejects_recreated_table_before_writing(workspace):
    run_memory(workspace)
    workspace.objects["table"]["TableId"] = "22222222-2222-2222-2222-222222222222"
    count = len(workspace.calls)
    with pytest.raises(AssertionError, match="SOURCE_TABLE_REPLACED"):
        run_memory(workspace)
    assert not any(method.startswith(("put_", "create_", "delete_", "set_")) for _, method, _ in workspace.calls[count:])


def test_memory_cleanup_removes_only_its_events_table_and_roles(workspace):
    namespace = run_memory(workspace)
    state = namespace["state"]
    for key in list(state.data["resources"]):
        if not key.startswith("memory."):
            state.forget(key, expected=state.get(key))
    untouched = {name for name in workspace.objects["roles"] if "-memory-" not in name}
    cells = build_cleanup().cells
    exec(next(c.source for c in cells if c.cell_type == "code" and "supported =" in c.source), namespace)
    exec(next(c.source for c in cells if c.cell_type == "code" and "control.delete_memory(" in c.source), namespace)
    assert not state.data["resources"]
    assert set(workspace.objects["roles"]) == untouched
    assert not workspace.events and not workspace.rows
    assert "identity_pool" not in workspace.objects
    deletion_order = [method for _, method, _ in workspace.calls if method.startswith("delete_")]
    assert deletion_order.index("delete_identity_pool") < deletion_order.index("delete_role")
