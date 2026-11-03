import json
from unittest.mock import Mock

import pytest

from santander_demo.aws_workshop.backend import Source
from santander_demo.aws_workshop.lifecycle import STAGES
from santander_demo.aws_workshop.seed import provision
from santander_demo.rag.corpus import corpus_digest, objects
from santander_demo.rag.seed import provision as provision_corpus

USERS = {
    label: {"oid": f"00000000-0000-4000-8000-00000000000{index}", "email": f"{label}@example.com"}
    for index, label in enumerate("abcd", 1)
}


def test_memory_omits_deleted_source_without_returning_old_content():
    memory, table = Mock(), Mock()
    memory.list_events.return_value = {"events": [{"payload": [{
        "conversational": {"content": {"text": '{"table_reference":"k2"}'}},
    }]}]}
    table.get_item.side_effect = [{"Item": {"allowed": True}}, {}]
    result = Source(table, memory, "memory").recall(
        {"iss": "pool", "sub": "person-c"}, "session-0123456789",
    )
    assert result["documents"] == []
    assert result["references_seen"] == 1
    assert table.get_item.call_count == 2


@pytest.mark.parametrize("current", STAGES)
def test_iac_lifecycle_changes_only_the_declared_synthetic_document_and_grant(current):
    table, writer = Mock(), Mock()
    table.batch_writer.return_value.__enter__ = Mock(return_value=writer)
    table.batch_writer.return_value.__exit__ = Mock(return_value=False)
    provision({
        "RequestType": "Update",
        "ResourceProperties": {"Users": {"c": "subject-c"}, "LifecycleStage": current},
    }, table)
    items = [call.kwargs["Item"] for call in writer.put_item.call_args_list]
    acl = next(item for item in items if item["pk"] == "ACL#subject-c" and item["sk"] == "k2")
    assert acl["allowed"] is (current != "revoked")
    assert {item["sk"] for item in items if item["pk"] == "DATA"} == (
        {"riscos", "fraude"} if current == "deleted" else {"riscos", "fraude", "k2"}
    )
    if current == "deleted":
        writer.delete_item.assert_called_once_with(Key={"pk": "DATA", "sk": "k2"})
    else:
        writer.delete_item.assert_not_called()
        document = next(item for item in items if item["pk"] == "DATA" and item["sk"] == "k2")
        assert json.loads(document["content"])[0]["revision"] == (
            1 if current == "baseline" else 3 if current == "reingested" else 2
        )


def test_corpus_revocation_changes_both_global_and_document_acl():
    values = objects("source", USERS, "revoked")
    global_acl = json.loads(values["acl/global-acl.json"])
    fraude = next(row for row in global_acl if row["keyPrefix"].endswith("/fraude/"))
    metadata = json.loads(values["documents/fraude/F1.txt.metadata.json"])
    for acl in [fraude["aclEntries"], metadata["accessControlList"]]:
        assert next(row for row in acl if row["Name"] == USERS["c"]["email"])["Access"] == "DENY"
        assert next(row for row in acl if row["Name"] == USERS["b"]["email"])["Access"] == "ALLOW"
    assert len({corpus_digest(USERS, current) for current in STAGES}) == len(STAGES)


def test_deleted_document_is_not_republished_and_ingestion_must_complete():
    s3, kb = Mock(), Mock()
    kb.get_data_source.return_value = {"dataSource": {"status": "AVAILABLE"}}
    kb.start_ingestion_job.return_value = {"ingestionJob": {"ingestionJobId": "job123"}}
    kb.get_ingestion_job.return_value = {"ingestionJob": {
        "status": "COMPLETE", "statistics": {"numberOfDocumentsFailed": 0},
    }}
    _, receipt = provision_corpus({
        "RequestType": "Update", "RequestId": "request123",
        "ResourceProperties": {
            "Bucket": "source", "KnowledgeBaseId": "kb123", "DataSourceId": "ds123",
            "Users": USERS, "LifecycleStage": "deleted",
            "CorpusDigest": corpus_digest(USERS, "deleted"),
        },
    }, s3, kb)
    assert receipt == {"IngestionJobId": "job123", "LifecycleStage": "deleted"}
    assert {call.kwargs["Key"] for call in s3.delete_object.call_args_list} == {
        "documents/fraude/F1.txt", "documents/fraude/F1.txt.metadata.json",
    }
    assert all("F1.txt" not in call.kwargs["Key"] for call in s3.put_object.call_args_list)
    assert all("VersionId" not in call.kwargs for call in s3.delete_object.call_args_list)
    kb.get_ingestion_job.assert_called_once()
