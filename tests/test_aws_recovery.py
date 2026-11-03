from unittest.mock import Mock

import pytest

from scripts import workshop_deploy


@pytest.fixture
def recovery(monkeypatch):
    cloud = Mock()
    cloud.describe_stacks.return_value = {"Stacks": [{"StackStatus": "ROLLBACK_COMPLETE"}]}
    cloud.get_template.return_value = {"TemplateBody": {
        "Description": "Workshop AWS - MCP JWT propagation and explicit per-person Cedar",
    }}
    cloud.get_paginator.return_value.paginate.return_value = [{
        "StackResourceSummaries": [{"ResourceStatus": "CREATE_FAILED"}],
    }]
    aws = Mock()
    aws.client.return_value = cloud
    monkeypatch.setattr(workshop_deploy, "session", lambda *args: aws)
    monkeypatch.setattr(workshop_deploy, "check_accounts", Mock())
    return cloud, {"project": "test-workshop"}


@pytest.mark.parametrize("status", ["CREATE_COMPLETE", "ROLLBACK_IN_PROGRESS", "UPDATE_ROLLBACK_COMPLETE"])
def test_recovery_never_deletes_successful_or_unfinished_stack(recovery, status):
    cloud, config = recovery
    cloud.describe_stacks.return_value["Stacks"][0]["StackStatus"] = status
    with pytest.raises(ValueError, match="RECOVERY_REQUIRES_COMPLETED_CREATE_ROLLBACK"):
        workshop_deploy.recover_failed_create(config, "platform", "bindings")
    cloud.delete_stack.assert_not_called()


def test_recovery_rejects_a_different_template(recovery):
    cloud, config = recovery
    cloud.get_template.return_value["TemplateBody"]["Description"] = "Another application"
    with pytest.raises(ValueError, match="OWNERSHIP_MISMATCH"):
        workshop_deploy.recover_failed_create(config, "platform", "bindings")
    cloud.delete_stack.assert_not_called()


def test_recovery_inspects_remaining_resources_on_every_page(recovery):
    cloud, config = recovery
    cloud.get_paginator.return_value.paginate.return_value = [
        {"StackResourceSummaries": [{"ResourceStatus": "DELETE_COMPLETE"}]},
        {"StackResourceSummaries": [{"ResourceStatus": "DELETE_FAILED"}]},
    ]
    with pytest.raises(ValueError, match="REMAINING_RESOURCES"):
        workshop_deploy.recover_failed_create(config, "platform", "bindings")
    cloud.delete_stack.assert_not_called()


def test_recovery_is_scoped_and_waits_for_deleted_empty_new_stack(recovery):
    cloud, config = recovery
    workshop_deploy.recover_failed_create(config, "platform", "bindings")
    cloud.delete_stack.assert_called_once_with(StackName="test-workshop-core-bindings")
    cloud.get_waiter.assert_called_once_with("stack_delete_complete")
    cloud.get_waiter.return_value.wait.assert_called_once_with(StackName="test-workshop-core-bindings")


def test_recovery_does_not_apply_to_other_phases(recovery):
    cloud, config = recovery
    with pytest.raises(ValueError, match="RECOVERY_IS_SCOPED"):
        workshop_deploy.recover_failed_create(config, "platform", "gateway")
    cloud.delete_stack.assert_not_called()


def test_failed_draft_marker_is_retained_but_does_not_block_scoped_stack_recovery(recovery):
    cloud, config = recovery
    cloud.get_template.return_value["TemplateBody"]["Description"] = (
        "Santander - geração assistida de rascunho Cedar, sem publicação"
    )
    cloud.get_paginator.return_value.paginate.return_value = [{"StackResourceSummaries": [
        {"ResourceStatus": "DELETE_COMPLETE"},
        {
            "LogicalResourceId": "Draft", "ResourceType": "Custom::AgentCorePolicyDraft",
            "PhysicalResourceId": "failed-17ac360b0425", "ResourceStatus": "DELETE_SKIPPED",
        },
    ]}]
    workshop_deploy.recover_failed_create(config, "platform", "policy-draft")
    cloud.delete_stack.assert_called_once_with(StackName="test-workshop-core-policy-draft")


@pytest.mark.parametrize("change", [
    {"PhysicalResourceId": "arn:aws:bedrock-agentcore:us-east-1:123456789012:policy-engine/engine/policy-generation/draft"},
    {"ResourceType": "AWS::Logs::LogGroup"},
    {"LogicalResourceId": "AnotherResource"},
    {"PhysicalResourceId": "failed-unknown"},
])
def test_draft_recovery_never_removes_a_generated_or_unrelated_retained_resource(recovery, change):
    cloud, config = recovery
    cloud.get_template.return_value["TemplateBody"]["Description"] = (
        "Santander - geração assistida de rascunho Cedar, sem publicação"
    )
    cloud.get_paginator.return_value.paginate.return_value = [{"StackResourceSummaries": [{
        "LogicalResourceId": "Draft", "ResourceType": "Custom::AgentCorePolicyDraft",
        "PhysicalResourceId": "failed-17ac360b0425", "ResourceStatus": "DELETE_SKIPPED", **change,
    }]}]
    with pytest.raises(ValueError, match="REMAINING_RESOURCES"):
        workshop_deploy.recover_failed_create(config, "platform", "policy-draft")
    cloud.delete_stack.assert_not_called()
