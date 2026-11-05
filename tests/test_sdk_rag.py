"""Controles antes da geração e validação da limpeza RAG."""

import ast
import hashlib
import io
import json
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cedarpy
import pytest
from botocore.exceptions import ClientError

from santander_demo.notebook_contracts import (
    RAG_MODULES,
    managed_source_configuration,
    native_knowledge_connector,
    validate_rag_archive,
)
from santander_demo.notebook_state import NotebookState
from scripts.sdk_notebook_lessons import build_cleanup, build_rag
from scripts.sdk_rag_cleanup import precheck
from scripts.sdk_rag_lesson import SERVER_SOURCE
from scripts.sdk_rag_runtime_reset import reset


def test_rag_waiter_waits_for_source_and_rejects_terminal_failure():
    cell = next(c.source for c in build_rag().cells
                if c.cell_type == "code" and "def wait_status(" in c.source)
    function = next(n for n in ast.parse(cell).body
                    if isinstance(n, ast.FunctionDef) and n.name == "wait_status")
    namespace = {"time": SimpleNamespace(monotonic=Mock(return_value=0), sleep=Mock())}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<wait-status>", "exec"), namespace)
    read = Mock(side_effect=[
        {"dataSource": {"status": "CREATING"}},
        {"dataSource": {"status": "AVAILABLE"}},
    ])
    assert namespace["wait_status"](read, "dataSource", "AVAILABLE", {"CREATING", "UPDATING"}) == {
        "dataSource": {"status": "AVAILABLE"},
    }
    assert read.call_count == 2
    with pytest.raises(AssertionError, match="RESOURCE_FAILED"):
        namespace["wait_status"](
            lambda: {"dataSource": {"status": "DELETE_UNSUCCESSFUL"}},
            "dataSource", "AVAILABLE", {"CREATING", "UPDATING"},
        )


def test_managed_source_readback_normalizes_only_observed_defaults():
    parameters = {"type": "S3", "aclEnabled": True, "filterConfiguration": {"inclusionPrefixes": ["documents/"]},
                  "connectionConfiguration": {"bucketName": "bucket"}}
    expected = {"type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
                "managedKnowledgeBaseConnectorConfiguration": {"connectorParameters": parameters}}
    readback = json.loads(json.dumps(expected))
    connector = readback["managedKnowledgeBaseConnectorConfiguration"]
    connector["connectorParameters"]["filterConfiguration"]["maxFileSizeInMegaBytes"] = "500"
    connector["connectorParameters"] = json.dumps(connector["connectorParameters"])
    connector["mediaExtractionConfiguration"] = {"imageExtractionConfiguration": {"imageExtractionStatus": "ENABLED"}}
    assert managed_source_configuration(readback) == expected
    assert isinstance(connector["connectorParameters"], str), "must not modify original response"
    altered = json.loads(connector["connectorParameters"])
    altered["aclEnabled"] = False
    connector["connectorParameters"] = json.dumps(altered)
    assert managed_source_configuration(readback) != expected
    altered["aclEnabled"] = True
    altered["filterConfiguration"]["maxFileSizeInMegaBytes"] = "999"
    connector["connectorParameters"] = json.dumps(altered)
    assert managed_source_configuration(readback) != expected


def test_native_connector_resolved_version_does_not_hide_other_versions():
    expected = {"mcp": {"connector": {"source": {"connectorId": "bedrock-knowledge-bases"}}}}
    current = json.loads(json.dumps(expected))
    source = current["mcp"]["connector"]["source"]
    source["version"] = "1.0.0"
    assert native_knowledge_connector(current) == expected
    assert source["version"] == "1.0.0"
    source["version"] = "2.0.0"
    assert native_knowledge_connector(current) != expected


@pytest.mark.parametrize("missing", [None, "bedrock_agentcore/runtime/app.py", "jwt/__init__.py"])
def test_rag_zip_requires_runtime_sdk_and_exact_source(missing):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in sorted(RAG_MODULES):
            if name != missing:
                archive.writestr(name, SERVER_SOURCE if name == "main.py" else "# fixture")
    if missing:
        with pytest.raises(ValueError, match="RAG_ARCHIVE_MISSING_MODULES"):
            validate_rag_archive(buffer.getvalue(), SERVER_SOURCE)
    else:
        validate_rag_archive(buffer.getvalue(), SERVER_SOURCE)
        with pytest.raises(ValueError, match="RAG_ARCHIVE_SOURCE_MISMATCH"):
            validate_rag_archive(buffer.getvalue(), "different")


def test_runtime_rebuild_changes_idempotency_token_after_confirmed_deletion():
    cell = next(c.source for c in build_rag().cells if c.cell_type == "code" and "control.create_agent_runtime(" in c.source)
    call = next(node for node in ast.walk(ast.parse(cell)) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "create_agent_runtime")
    expression = next(keyword.value for keyword in call.keywords if keyword.arg == "clientToken")
    compiled = compile(ast.Expression(expression), "<client-token>", "eval")
    namespace = {"uuid": uuid, "NAME_PREFIX": "workshop", "artifact_hash": "same-artifact",
                 "previous_runtime_id": "initial"}
    first = eval(compiled, namespace)
    assert eval(compiled, namespace) == first
    namespace["previous_runtime_id"] = "deleted-runtime-one"
    second = eval(compiled, namespace)
    assert second != first and eval(compiled, namespace) == second
    namespace["previous_runtime_id"] = "deleted-runtime-two"
    assert eval(compiled, namespace) not in {first, second}


def test_rag_runtime_reset_preserves_knowledge_base_gateway_policies_and_other_lessons():
    resources = {
        "rag.runtime": {"id": "runtime"},
        "rag.logs": {"name": "/aws/bedrock-agentcore/runtimes/runtime-DEFAULT"},
        "rag.runtime_role": {"name": "runtime-role", "policy_name": "Lesson16Runtime"},
        "rag.artifact": {"bucket": "artifact-bucket", "key": "rag/artifact.zip"},
        "rag.knowledge_base": {"id": "knowledge-base"}, "rag.data_source": {"id": "source"},
        "rag.target": {"id": "target"}, "rag.policy.analista": {"id": "policy"},
        "gateway.instance": {"id": "gateway"}, "runtime.instance": {"id": "mcp"},
    }
    preserved = {key: value for key, value in resources.items()
                 if key not in {"rag.runtime", "rag.logs", "rag.runtime_role", "rag.artifact"}}
    state = SimpleNamespace(data={"resources": resources, "status": "ACTIVE"}, get=resources.get)

    def forget(key, *, expected):
        assert resources[key] == expected
        del resources[key]

    state.forget = forget
    control, iam, logs, s3 = Mock(), Mock(), Mock(), Mock()
    logs.describe_log_groups.return_value = {"logGroups": []}
    iam.list_role_policies.return_value = {"PolicyNames": ["Lesson16Runtime"]}

    class NotFound(Exception):
        pass

    s3.exceptions.NoSuchKey = NotFound
    s3.get_object.side_effect = NotFound
    namespace = {"CLEANUP_SCOPE": "rag-runtime", "state": state, "control": control,
                 "iam": iam, "logs": logs, "s3": s3, "ACCOUNT_ID": "123456789012",
                 "wait_deleted": lambda read, not_found: None}
    for cell in reset():
        if cell.cell_type == "code":
            exec(cell.source, namespace)
    assert resources == preserved and state.data["status"] == "ACTIVE"
    control.delete_gateway_target.assert_not_called()
    control.delete_policy.assert_not_called()
    s3.delete_bucket.assert_not_called()
    # Todas as outras células de exclusão ficam inativas neste escopo.
    notebook = build_cleanup()
    checked = False
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        if "supported =" in cell.source:
            checked = True
            continue
        if checked and '== "rag-runtime":' not in cell.source:
            exec(cell.source, {"CLEANUP_SCOPE": "rag-runtime"})


@pytest.fixture
def runtime():
    config = {
        "issuer": "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_test", "region": "us-west-2",
        "client_id": "client", "knowledge_base_id": "KB12345678",
        "gateway_url": "https://example.invalid/mcp", "model_id": "amazon.nova-lite-v1:0",
        "documents_by_subject": {"analyst": ["R1"], "auditor": ["F1"]},
        "document_uris": {"R1": "s3://synthetic/documents/R1.txt", "F1": "s3://synthetic/documents/F1.txt"},
    }
    aws = Mock()
    aws.client.return_value.converse.return_value = {
        "output": {"message": {"content": [{"text": "Resposta [R1]"}]}},
        "ResponseMetadata": {"RequestId": "model-request"},
    }
    app = SimpleNamespace(entrypoint=lambda function: function)
    with (
        patch.dict("os.environ", {"WORKSHOP_RAG": json.dumps(config)}),
        patch("boto3.Session", return_value=aws),
        patch("bedrock_agentcore.runtime.BedrockAgentCoreApp", return_value=app),
        patch("jwt.PyJWKClient") as jwks,
    ):
        jwks.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key="key")
        namespace = {"__name__": "test_runtime"}
        exec(SERVER_SOURCE, namespace)
    return config, aws, namespace


def retrieval_response(runtime, document="R1"):
    config, _, _ = runtime
    return SimpleNamespace(
        headers={"x-amzn-requestid": "gateway-request", "content-type": "application/json"},
        raise_for_status=lambda: None,
        json=lambda: {"jsonrpc": "2.0", "id": 16, "result": {"structuredContent": {
            "retrievalResults": [{
                "metadata": {"document_id": document},
                "location": {"s3Location": {"uri": config["document_uris"][document]}},
                "content": {"text": "Trecho sintético " + document},
            }],
        }}},
    )


def invoke(runtime, payload, *, subject="analyst", response=None):
    _, _, namespace = runtime
    claims = {"sub": subject, "token_use": "id"}
    with patch("jwt.decode", return_value=claims), patch("httpx.post", return_value=response) as http:
        result = namespace["run"](
            payload, SimpleNamespace(request_headers={"Authorization": "Bearer opaque-test-token"}),
        )
    return result, http


def test_runtime_derives_user_context_and_only_generates_from_authorized_chunks(runtime):
    config, aws, _ = runtime
    result, http = invoke(runtime, {"question": "Quais procedimentos?"}, response=retrieval_response(runtime))
    assert result["generated"] and result["document_ids"] == ["R1"]
    assert result["model_request_id"] == "model-request" and result["gateway_request_id"] == "gateway-request"
    arguments = http.call_args.kwargs["json"]["params"]["arguments"]
    assert arguments["userContext"] == {"userId": "analyst"}
    completion = aws.client.return_value.converse.call_args.kwargs
    assert completion["modelId"] == config["model_id"]
    assert "Trecho sintético R1" in completion["messages"][0]["content"][0]["text"]
    assert "F1" not in json.dumps(completion)


@pytest.mark.parametrize("payload,subject", [
    ({"question": "x", "userContext": {"userId": "auditor"}}, "analyst"),
    ({"question": "x"}, "unregistered"),
])
def test_identity_overrides_and_unknown_subject_never_call_gateway_or_model(runtime, payload, subject):
    _, aws, _ = runtime
    with pytest.raises(AssertionError), patch("httpx.post") as http:
        invoke(runtime, payload, subject=subject)
    http.assert_not_called()
    aws.client.return_value.converse.assert_not_called()


def test_unexpected_acl_result_never_reaches_model(runtime):
    _, aws, _ = runtime
    with pytest.raises(AssertionError, match="ACL_RESULT_MISMATCH"):
        invoke(runtime, {"question": "x"}, response=retrieval_response(runtime, "F1"))
    aws.client.return_value.converse.assert_not_called()


@pytest.mark.parametrize("uri,accepted", [
    ("https://synthetic.s3.us-west-2.amazonaws.com/documents/R1.txt", True),
    ("https://other.s3.us-west-2.amazonaws.com/documents/R1.txt", False),
    ("https://synthetic.s3.us-east-1.amazonaws.com/documents/R1.txt", False),
])
def test_native_source_uri_stays_bound_to_expected_bucket_key_and_region(runtime, uri, accepted):
    response = retrieval_response(runtime)
    document = response.json()
    document["result"]["structuredContent"]["retrievalResults"][0]["location"]["s3Location"]["uri"] = uri
    response.json = lambda: document
    if accepted:
        result, _ = invoke(runtime, {"question": "x"}, response=response)
        assert result["generated"]
    else:
        with pytest.raises(AssertionError, match="ACL_RESULT_MISMATCH"):
            invoke(runtime, {"question": "x"}, response=response)
        runtime[1].client.return_value.converse.assert_not_called()


def test_direct_retrieve_requires_actual_access_denied(runtime):
    _, aws, _ = runtime
    api = aws.client.return_value
    api.retrieve.side_effect = ClientError({
        "Error": {"Code": "AccessDeniedException", "Message": "denied"},
        "ResponseMetadata": {"RequestId": "iam-request"},
    }, "Retrieve")
    result, http = invoke(runtime, {"operation": "probe_direct_retrieval"})
    assert result["direct_retrieval"] == "IAM_DENY" and result["request_id"] == "iam-request"
    http.assert_not_called()
    api.converse.assert_not_called()
    api.retrieve.side_effect = ClientError({"Error": {"Code": "ThrottlingException", "Message": "retry"}}, "Retrieve")
    with pytest.raises(AssertionError):
        invoke(runtime, {"operation": "probe_direct_retrieval"})


def test_cedar_requires_subject_bound_context_and_expected_issuer_audience():
    cell = next(c.source for c in build_rag().cells if c.cell_type == "code" and 'key = "rag.policy."' in c.source)
    loop = ast.parse(cell).body[0]
    assignment = ast.Module(body=loop.body[:2], type_ignores=[])
    ns = {
        "json": json, "entry": {"sub": "analyst"}, "ISSUER": "https://issuer.invalid",
        "client": {"id": "client"}, "gateway_entry": {"arn": "arn:aws:bedrock-agentcore:us-west-2:123456789012:gateway/example"},
    }
    exec(compile(assignment, "<cedar>", "exec"), ns)
    principal = {"type": "AgentCore::OAuthUser", "id": "analyst"}
    request = {"principal": principal, "action": {"type": "AgentCore::Action", "id": "rag___Retrieve"},
               "resource": {"type": "AgentCore::Gateway", "id": ns["gateway_entry"]["arn"]}}
    for subject, issuer, audience, expected in (
        ("analyst", ns["ISSUER"], "client", True), ("auditor", ns["ISSUER"], "client", False),
        ("analyst", "https://wrong.invalid", "client", False), ("analyst", ns["ISSUER"], "other", False),
    ):
        tags = {"iss": issuer, "aud": audience, "token_use": "id"}
        result = cedarpy.is_authorized(
            {**request, "context": {"input": {"userContext": {"userId": subject}}}},
            ns["statement"], [{"uid": principal, "attrs": {}, "parents": [], "tags": tags}],
        )
        assert result.allowed is expected


def test_cleanup_rejects_changed_role_before_delete():
    trust = {"Version": "2012-10-17", "Statement": []}
    expected = {"Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::one/*"}]}
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    entry = {"name": "prefix-rag-knowledge", "arn": "arn:role", "trust_sha256": digest(trust),
             "policy_name": "Lesson16KnowledgeSource", "policy_sha256": digest(expected)}
    state = SimpleNamespace(data={"resources": {"rag.knowledge_role": entry}}, get=lambda key: entry if key == "rag.knowledge_role" else None)
    iam = Mock()
    iam.get_role.return_value = {"Role": {"Arn": entry["arn"], "AssumeRolePolicyDocument": trust, "Tags": []}}
    iam.list_attached_role_policies.return_value = {"AttachedPolicies": []}
    iam.list_role_policies.return_value = {"PolicyNames": [entry["policy_name"]]}
    iam.get_role_policy.return_value = {"PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}}
    namespace = {"aws": Mock(), "state": state, "NAME_PREFIX": "prefix", "iam": iam,
                 "owned": lambda tags: None, "hashlib": hashlib, "json": json}
    with pytest.raises(AssertionError, match="RAG_ROLE_CHANGED"):
        exec(precheck(), namespace)
    assert all(not call[0].startswith("delete_") for call in iam.method_calls)


@pytest.mark.parametrize("drift", [None, "account", "id", "role", "configuration", "missing_source", "foreign_source"])
def test_knowledge_base_cleanup_binds_physical_id_account_and_configuration(drift):
    account, region = "123456789012", "us-west-2"
    config = {"type": "MANAGED", "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"}}
    entry = {
        "id": "KB12345678", "arn": f"arn:aws:bedrock:{region}:{account}:knowledge-base/KB12345678",
        "role_arn": f"arn:aws:iam::{account}:role/prefix-rag-knowledge",
        "configuration_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
    }
    current = {"knowledgeBaseArn": entry["arn"], "name": "prefix_rag",
               "roleArn": entry["role_arn"], "knowledgeBaseConfiguration": config}
    if drift == "account":
        entry["arn"] = current["knowledgeBaseArn"] = entry["arn"].replace(account, "999999999999")
    elif drift == "id":
        current["knowledgeBaseArn"] = entry["arn"].replace("KB12345678", "OTHER12345")
    elif drift == "role":
        current["roleArn"] += "-other"
    elif drift == "configuration":
        current["knowledgeBaseConfiguration"] = {"type": "VECTOR"}
    resources = {"rag.knowledge_base": entry}
    state = SimpleNamespace(data={"resources": resources}, get=resources.get,
                            require=lambda key, lesson: resources[key])
    api = Mock()
    api.get_knowledge_base.return_value = {"knowledgeBase": current}
    api.list_data_sources.return_value = {"dataSourceSummaries": []}
    if drift == "foreign_source":
        api.list_data_sources.return_value = {"dataSourceSummaries": [{"dataSourceId": "UNKNOWN"}]}
    elif drift == "missing_source":
        resources["rag.data_source"] = {"id": "DS12345678", "knowledge_base_id": entry["id"]}
        api.exceptions.ResourceNotFoundException = type("NotFound", (Exception,), {})
        api.get_data_source.side_effect = api.exceptions.ResourceNotFoundException
    namespace = {"aws": SimpleNamespace(client=lambda service: api), "state": state,
                 "NAME_PREFIX": "prefix", "PARTITION": "aws", "REGION": region, "ACCOUNT_ID": account,
                 "hashlib": hashlib, "json": json}
    if drift not in {None, "missing_source"}:
        with pytest.raises(AssertionError):
            exec(precheck(), namespace)
    else:
        exec(precheck(), namespace)
    api.list_tags_for_resource.assert_not_called()
    assert all(not call[0].startswith("delete_") for call in api.method_calls)


@pytest.mark.parametrize("status,timeout", [
    ("AVAILABLE", False), ("DELETING", False), ("ABSENT", False),
    ("DELETING", True), ("DELETE_UNSUCCESSFUL", False),
])
def test_data_source_cleanup_resumes_without_duplicate_delete_and_keeps_state_on_timeout(tmp_path, status, timeout):
    state = NotebookState(tmp_path, account_id="123456789012", region="us-west-2")
    entry = state.record("rag.data_source", {"id": "DS12345678", "knowledge_base_id": "KB12345678"}, lesson="16")
    state.record("rag.ingestion", {"id": "JOB1234567"}, lesson="16")
    api, waiter = Mock(), Mock()
    api.exceptions.ResourceNotFoundException = type("NotFound", (Exception,), {})
    if status == "ABSENT":
        api.get_data_source.side_effect = api.exceptions.ResourceNotFoundException
    else:
        api.get_data_source.return_value = {"dataSource": {"status": status}}
    if timeout:
        waiter.side_effect = TimeoutError("CLEANUP_DELETE_TIMEOUT")
    cell = next(c.source for c in build_cleanup().cells
                if c.cell_type == "code" and "bedrock.delete_data_source(" in c.source)
    namespace = {"state": state, "bedrock": api, "wait_deleted": waiter}
    if timeout:
        with pytest.raises(TimeoutError, match="CLEANUP_DELETE_TIMEOUT"):
            exec(cell, namespace)
        assert state.get("rag.data_source") == entry
        assert state.get("rag.ingestion")
    elif status == "DELETE_UNSUCCESSFUL":
        with pytest.raises(AssertionError, match="DATA_SOURCE_DELETE_NOT_READY"):
            exec(cell, namespace)
        assert state.get("rag.data_source") == entry
    else:
        exec(cell, namespace)
        assert not state.get("rag.data_source") and not state.get("rag.ingestion")
    if status == "AVAILABLE":
        api.delete_data_source.assert_called_once_with(knowledgeBaseId=entry["knowledge_base_id"], dataSourceId=entry["id"])
    else:
        api.delete_data_source.assert_not_called()
    if status in {"AVAILABLE", "DELETING"}:
        assert waiter.call_args.kwargs == {"timeout": 840}
    else:
        waiter.assert_not_called()


def test_cleanup_validates_all_dependencies_before_first_rag_delete():
    cells = [c.source for c in build_cleanup().cells if c.cell_type == "code"]
    validate = next(i for i, source in enumerate(cells) if "supported =" in source)
    delete = next(i for i, source in enumerate(cells) if "control.delete_agent_runtime(" in source)
    assert "RAG_ROLE_CHANGED" in cells[validate] and "UNREGISTERED_RAG_OBJECTS" in cells[validate]
    assert "UNREGISTERED_GATEWAY_TARGETS" in cells[validate] and validate < delete
    assert 'state.get("rag.target")' in cells[validate] and 'state.get("rag.policy.auditor")' in cells[validate]
