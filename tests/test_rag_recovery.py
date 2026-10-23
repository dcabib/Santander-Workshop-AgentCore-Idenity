from unittest.mock import MagicMock

import pytest

from infra.rag.generate import data
from scripts.rag_recover import execute, plan


def test_recovery_only_imports_resources_retained_by_the_exact_failed_stack():
    session = MagicMock()
    cfn, sts, kb = MagicMock(), MagicMock(), MagicMock()
    session.client.side_effect = {
        "cloudformation": cfn,
        "sts": sts,
        "bedrock-agent": kb,
    }.__getitem__
    arn = "arn:aws:cloudformation:us-east-1:111111111111:stack/rag-data/uuid"
    cfn.describe_stacks.return_value = {
        "Stacks": [
            {
                "StackId": arn,
                "StackName": "rag-data",
                "StackStatus": "ROLLBACK_COMPLETE",
                "Parameters": [{"ParameterKey": "Project", "ParameterValue": "rag"}],
            }
        ]
    }
    sts.get_caller_identity.return_value = {"Account": "111111111111"}
    cfn.get_template.return_value = {"TemplateBody": data()}
    cfn.list_stack_resources.return_value = {
        "StackResourceSummaries": [
            {
                "LogicalResourceId": "KnowledgeBase",
                "PhysicalResourceId": "KB123",
                "ResourceStatus": "DELETE_SKIPPED",
            },
            {
                "LogicalResourceId": "SourceBucket",
                "PhysicalResourceId": "owned-corpus",
                "ResourceStatus": "DELETE_SKIPPED",
            },
            {"LogicalResourceId": "KnowledgeRole", "ResourceStatus": "DELETE_COMPLETE"},
            {"LogicalResourceId": "DataSource", "ResourceStatus": "DELETE_SKIPPED"},
        ]
    }
    kb.get_knowledge_base.return_value = {
        "knowledgeBase": {
            "name": "rag",
            "roleArn": "arn:aws:iam::111111111111:role/old",
            "knowledgeBaseConfiguration": {"type": "MANAGED"},
        }
    }
    kb.list_data_sources.return_value = {"dataSourceSummaries": []}
    proposal = plan(session, arn)
    assert set(proposal["template"]["Resources"]) == {"SourceBucket", "KnowledgeBase"}
    assert proposal["imports"][1]["ResourceIdentifier"] == {"KnowledgeBaseId": "KB123"}
    assert not cfn.delete_stack.called and not cfn.create_change_set.called
    cfn.list_stack_resources.return_value["StackResourceSummaries"].append(
        {
            "LogicalResourceId": "Unexpected",
            "ResourceStatus": "DELETE_SKIPPED",
        }
    )
    with pytest.raises(ValueError, match="UNEXPECTED_RETAINED"):
        plan(session, arn)


def test_recovery_execution_uses_only_cloudformation_and_requires_exact_arn():
    session = MagicMock()
    cfn = session.client.return_value
    cfn.create_change_set.return_value = {"Id": "changeset", "StackId": "new-stack"}
    cfn.describe_change_set.return_value = {"Changes": [{"ResourceChange": {"Action": "Import"}}]}
    proposal = {"stack_id": "old-stack", "stack_name": "rag-data", "template": {}, "imports": []}
    with pytest.raises(ValueError, match="CONFIRMATION"):
        execute(session, proposal, "other")
    assert not cfn.delete_stack.called
    assert execute(session, proposal, "old-stack")["recovery"] == "IMPORT_COMPLETE"
    assert [c.args[0] for c in session.client.call_args_list] == ["cloudformation"]
    assert cfn.create_change_set.call_args.kwargs["ChangeSetType"] == "IMPORT"
