"""Contratos do SDK e retomada das células sem uma conta previamente implantada."""

import ast
import base64
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.validate import validate_parameters

from scripts.sdk_notebook_lessons import (
    build_cleanup,
    build_gateway,
    build_identity,
    build_policy,
    build_policy_authoring,
    build_runtime,
)

ACCOUNT = "123456789012"
REGION = "us-west-2"


class AWSContract:
    """Valida inputs com botocore; respostas simuladas não são aceite AWS."""

    region_name = REGION

    def __init__(self):
        model_session = boto3.Session(
            region_name=REGION, aws_access_key_id="model-only",
            aws_secret_access_key="model-only",
        )
        self.clients = {
            name: model_session.client(name) for name in (
                "sts", "iam", "lambda", "logs", "cognito-idp", "secretsmanager",
                "bedrock-agentcore-control", "bedrock-agentcore", "s3",
            )
        }
        self.calls = []
        self.objects = {"roles": {}, "users": {}, "role_policies": {}, "clients": {}}

    def client(self, service):
        model = self.clients[service]
        owner = self

        class Client:
            exceptions = model.exceptions
            meta = model.meta

            def get_waiter(self, name):
                return SimpleNamespace(wait=lambda **kwargs: None)

            def __getattr__(self, method):
                operation = model.meta.method_to_api_mapping[method]

                def call(**kwargs):
                    shape = model.meta.service_model.operation_model(operation).input_shape
                    if shape:
                        validate_parameters(kwargs, shape)
                    owner.calls.append((service, method, deepcopy(kwargs)))
                    return deepcopy(owner.respond(service, method, kwargs))

                return call

        return Client()

    def respond(self, service, method, args):
        objects = self.objects
        if method == "get_caller_identity":
            return {
                "Account": ACCOUNT, "Arn": f"arn:aws:iam::{ACCOUNT}:role/Participant",
                "ResponseMetadata": {"RequestId": "sts-test"},
            }
        if method == "create_user_pool":
            objects["pool"] = {
                "Id": REGION + "_TestPool", "Arn": f"arn:aws:cognito-idp:{REGION}:{ACCOUNT}:userpool/test",
                "Name": args["PoolName"], "UserPoolTags": args["UserPoolTags"],
                "AdminCreateUserConfig": args["AdminCreateUserConfig"],
            }
        if method in {"create_user_pool", "describe_user_pool"}:
            return {"UserPool": objects["pool"]}
        if method == "create_user_pool_client":
            client_id = "appclient" + str(len(objects["clients"]) + 1)
            objects["client"] = {**args, "ClientId": client_id}
            objects["clients"][client_id] = objects["client"]
        if method == "update_user_pool_client":
            objects["clients"][args["ClientId"]].update(args)
            return {"UserPoolClient": objects["clients"][args["ClientId"]]}
        if method == "describe_user_pool_client":
            return {"UserPoolClient": objects["clients"][args["ClientId"]]}
        if method == "create_user_pool_client":
            return {"UserPoolClient": objects["client"]}
        if method == "get_random_password":
            return {"RandomPassword": "Synthetic-Password-For-Test-Only-123!"}
        if method == "create_secret":
            objects["secret"] = {
                "ARN": f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:demo-ABCDEF",
                "Name": args["Name"], "Tags": args["Tags"], "SecretString": args["SecretString"],
            }
            return {"ARN": objects["secret"]["ARN"]}
        if method == "describe_secret":
            return {key: value for key, value in objects["secret"].items() if key != "SecretString"}
        if method == "get_secret_value":
            return {"SecretString": objects["secret"]["SecretString"]}
        if method == "admin_create_user":
            person = {
                "Username": args["Username"], "UserStatus": "FORCE_CHANGE_PASSWORD",
                "Attributes": [{"Name": "sub", "Value": args["Username"] + "-subject"}],
            }
            objects["users"][args["Username"]] = person
            return {"User": person}
        if method == "admin_set_user_password":
            objects["users"][args["Username"]]["UserStatus"] = "CONFIRMED"
            return {}
        if method == "create_log_group":
            objects["logs"] = {"tags": args["tags"]}
            return {}
        if method == "list_tags_for_resource":
            return objects["logs"] if service == "logs" else {"tags": objects["gateway"]["tags"]}
        if method == "put_retention_policy":
            return {}
        if method == "create_role":
            objects["roles"][args["RoleName"]] = {
                "RoleName": args["RoleName"],
                "Arn": f"arn:aws:iam::{ACCOUNT}:role/{args['RoleName']}",
                "Tags": args["Tags"],
                "AssumeRolePolicyDocument": json.loads(args["AssumeRolePolicyDocument"]),
            }
        if method in {"create_role", "get_role"}:
            return {"Role": objects["roles"][args["RoleName"]]}
        if method == "put_role_policy":
            objects["role_policies"][args["RoleName"], args["PolicyName"]] = json.loads(args["PolicyDocument"])
            return {}
        if method == "get_role_policy":
            policy = objects["role_policies"].get((args["RoleName"], args["PolicyName"]))
            if policy is None:
                raise self.clients["iam"].exceptions.NoSuchEntityException(
                    {"Error": {"Code": "NoSuchEntity", "Message": "not created"}}, method,
                )
            return {"PolicyDocument": policy}
        if method == "update_assume_role_policy":
            objects["roles"][args["RoleName"]]["AssumeRolePolicyDocument"] = json.loads(args["PolicyDocument"])
            return {}
        if method == "create_function":
            objects["function"] = {"Configuration": {
                "FunctionArn": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{args['FunctionName']}",
                "Description": args["Description"],
                "FunctionName": args["FunctionName"], "Role": args["Role"], "State": "Active",
                "CodeSha256": base64.b64encode(hashlib.sha256(args["Code"]["ZipFile"]).digest()).decode(),
            }}
            return objects["function"]["Configuration"]
        if method == "get_function":
            return objects["function"]
        if method == "create_gateway":
            objects["gateway"] = {
                "name": args["name"], "protocolType": args["protocolType"],
                "gatewayId": "gateway-abcdefghij",
                "gatewayArn": f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}:gateway/gateway-abcdefghij",
                "gatewayUrl": f"https://gateway-abcdefghij.gateway.bedrock-agentcore.{REGION}.amazonaws.com/mcp",
                "roleArn": args["roleArn"], "status": "READY", "tags": args["tags"],
                "authorizerType": args["authorizerType"],
                "authorizerConfiguration": args["authorizerConfiguration"],
            }
        if method in {"create_gateway", "get_gateway"}:
            return objects["gateway"]
        if method == "create_gateway_target":
            objects["target"] = {
                "targetId": "target-id", "status": "READY",
                "targetConfiguration": args["targetConfiguration"],
                "credentialProviderConfigurations": args["credentialProviderConfigurations"],
            }
        if method in {"create_gateway_target", "get_gateway_target"}:
            return objects["target"]
        raise AssertionError((service, method))


def provisioning_cells():
    for cell in build_gateway().cells:
        if cell.cell_type == "code":
            if "import jwt" in cell.source:
                break
            yield cell.source


def test_gateway_creates_resources_with_current_sdk_and_resumes_without_recreation(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='empty-workshop'\n")
    monkeypatch.chdir(tmp_path)
    aws = AWSContract()
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied):
        for run in range(2):
            namespace = {}
            for source in provisioning_cells():
                exec(compile(source, "gateway-cell", "exec"), namespace)
            if run == 0:
                first_creates = [(service, method) for service, method, _ in aws.calls if method.startswith("create_")]
    all_creates = [(service, method) for service, method, _ in aws.calls if method.startswith("create_")]
    assert all_creates == first_creates
    assert ("bedrock-agentcore-control", "create_gateway") in all_creates
    assert ("lambda", "create_function") in all_creates
    function_request = next(args for _, method, args in aws.calls if method == "create_function")
    assert "Tags" not in function_request
    assert ("cognito-idp", "create_user_pool") in all_creates
    assert sum(method == "admin_set_user_password" for _, method, _ in aws.calls) == 2
    assert sum(method == "put_role_policy" for _, method, _ in aws.calls) == 2
    assert sum(method == "update_assume_role_policy" for _, method, _ in aws.calls) == 1
    persisted = namespace["state"].path.read_text()
    assert "Synthetic-Password" not in persisted
    assert not (tmp_path / "config").exists()
    gateway_role = aws.objects["roles"][namespace["GATEWAY_ROLE_NAME"]]
    assert gateway_role["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] == {
        "StringEquals": {"aws:SourceAccount": ACCOUNT},
        "ArnLike": {"aws:SourceArn": aws.objects["gateway"]["gatewayArn"]},
    }


@pytest.mark.parametrize("status", [200, 403, 500])
def test_authentication_check_never_accepts_wrong_status(status):
    cell = next(c for c in build_gateway().cells if c.cell_type == "code" and '("anonymous", {})' in c.source)
    with patch("httpx.post", return_value=SimpleNamespace(status_code=status, headers={})):
        with pytest.raises(AssertionError):
            exec(cell.source, {
                "REGION": REGION,
                "GATEWAY_URL": f"https://gateway-abcdefghij.gateway.bedrock-agentcore.{REGION}.amazonaws.com/mcp",
            })


def test_changed_ownership_stops_before_reusing_gateway_resources(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    monkeypatch.chdir(tmp_path)
    aws = AWSContract()
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied):
        namespace = {}
        for source in provisioning_cells():
            exec(source, namespace)
        aws.objects["pool"]["UserPoolTags"] = {"workshop-run": "another-run"}
        previous = len(aws.calls)
        namespace = {}
        with pytest.raises(RuntimeError, match="RESOURCE_OWNERSHIP_MISMATCH"):
            for source in provisioning_cells():
                exec(source, namespace)
    assert [method for _, method, _ in aws.calls[previous:]] == ["get_caller_identity", "describe_user_pool"]


@pytest.mark.parametrize("field,value", [
    ("Description", "another-execution"),
    ("Role", f"arn:aws:iam::{ACCOUNT}:role/AnotherRole"),
    ("CodeSha256", "unexpected-code"),
    ("FunctionArn", f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:unregistered"),
])
def test_lambda_identity_changes_stop_notebook_reuse(tmp_path, monkeypatch, field, value):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    monkeypatch.chdir(tmp_path)
    aws = AWSContract()
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied):
        namespace = {}
        for source in provisioning_cells():
            exec(source, namespace)
        aws.objects["function"]["Configuration"][field] = value
        call_count = len(aws.calls)
        namespace = {}
        with pytest.raises(AssertionError):
            for source in provisioning_cells():
                exec(source, namespace)
    assert not any(service == "bedrock-agentcore-control" for service, _, _ in aws.calls[call_count:])
    namespace["state"].data["resources"] = {
        key: value for key, value in namespace["state"].data["resources"].items()
        if key in {"gateway.tool_lambda", "gateway.lambda_role"}
    }
    check = next(c for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    call_count = len(aws.calls)
    with pytest.raises(AssertionError):
        exec(check.source, namespace)
    assert all(not method.startswith(("create_", "put_", "delete_", "update_")) for _, method, _ in aws.calls[call_count:])


def test_cleanup_refuses_dependencies_before_any_mutation(tmp_path):
    from santander_demo.notebook_state import NotebookState

    state = NotebookState(tmp_path, account_id=ACCOUNT, region=REGION)
    state.record("registry.record", {"id": "record-from-later-lesson"}, lesson="07")
    aws = AWSContract()
    check = next(c for c in build_cleanup().cells if c.cell_type == "code" and "supported =" in c.source)
    with pytest.raises(RuntimeError, match="CLEANUP_DEPENDENCIES_NOT_SUPPORTED"):
        exec(check.source, {"aws": aws, "state": state})
    assert aws.calls == []


def test_notebook_code_is_valid_and_independent_of_legacy_predeployment():
    for notebook in (
        build_gateway(), build_identity(), build_runtime(), build_policy(), build_policy_authoring(),
        build_cleanup(),
    ):
        for cell in notebook.cells:
            if cell.cell_type == "code":
                compile(cell.source, "sdk-cell", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
                for forbidden in ("AWSWorkshop(", "stack_outputs(", "aws.workshop.json", "cloudformation"):
                    assert forbidden not in cell.source
                for administrative_read in ("admin_get_user(", "list_users(", "admin_initiate_auth("):
                    assert administrative_read not in cell.source


def test_existing_client_auth_flow_can_migrate_without_changing_audience(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    monkeypatch.chdir(tmp_path)
    aws = AWSContract()
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    with patch("boto3.Session", return_value=aws), patch("httpx.post", return_value=denied):
        namespace = {}
        for source in provisioning_cells():
            exec(source, namespace)
        before = deepcopy(aws.objects["client"])
        aws.objects["client"]["ExplicitAuthFlows"] = [
            "ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH",
        ]
        namespace = {}
        for source in provisioning_cells():
            exec(source, namespace)
    after = aws.objects["client"]
    assert after["ClientId"] == before["ClientId"]
    for field in ("IdTokenValidity", "AccessTokenValidity", "RefreshTokenValidity", "TokenValidityUnits"):
        assert after[field] == before[field]
    assert set(after["ExplicitAuthFlows"]) == {"ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"}
    updates = [method for _, method, _ in aws.calls if method == "update_user_pool_client"]
    assert len(updates) == 1


@pytest.mark.parametrize("failures,error_code,message,expected_calls,passes", [
    (2, "ValidationException", "Gateway service is not authorized to perform AssumeRole on Gateway role.", 3, True),
    (20, "ValidationException", "Gateway service is not authorized to perform AssumeRole on Gateway role.", 12, False),
    (1, "AccessDeniedException", "Caller not authorized", 1, False),
    (1, "ValidationException", "Invalid Lambda ARN", 1, False),
])
def test_target_retries_are_bounded_identical_and_limited_to_role_propagation(
    tmp_path, monkeypatch, failures, error_code, message, expected_calls, passes,
):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n")
    monkeypatch.chdir(tmp_path)
    aws = AWSContract()
    original_response = aws.respond
    attempts = 0

    def response(service, method, args):
        nonlocal attempts
        if method == "create_gateway_target":
            attempts += 1
            if attempts <= failures:
                raise ClientError({"Error": {"Code": error_code, "Message": message}}, "CreateGatewayTarget")
        return original_response(service, method, args)

    aws.respond = response
    denied = SimpleNamespace(status_code=401, headers={"x-amzn-requestid": "deny-test"})
    namespace = {}
    with (
        patch("boto3.Session", return_value=aws),
        patch("httpx.post", return_value=denied),
        patch("time.sleep") as sleep,
    ):
        if passes:
            for source in provisioning_cells():
                exec(source, namespace)
        else:
            with pytest.raises(ClientError):
                for source in provisioning_cells():
                    exec(source, namespace)
        assert sleep.call_count == expected_calls - 1
    requests = [args for _, method, args in aws.calls if method == "create_gateway_target"]
    assert len(requests) == expected_calls
    assert all(request == requests[0] for request in requests)
    assert sum(method == "update_assume_role_policy" for _, method, _ in aws.calls) == 1
    assert bool(namespace["state"].get("gateway.lambda_target")) == passes
