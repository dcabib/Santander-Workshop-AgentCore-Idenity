from unittest.mock import Mock

import pytest

from santander_demo.aws_workshop.log_retention import provision

GROUP = "/aws/bedrock-agentcore/runtimes/santander_workshop_core_aws-abc123-DEFAULT"


def test_retention_never_creates_or_deletes_a_service_owned_log_group():
    logs = Mock()
    logs.describe_log_groups.return_value = {"logGroups": [{"logGroupName": GROUP}]}
    assert provision({"RequestType": "Create", "ResourceProperties": {"LogGroup": GROUP}}, logs) == {
        "LogGroup": GROUP,
    }
    logs.put_retention_policy.assert_called_once_with(logGroupName=GROUP, retentionInDays=7)
    logs.create_log_group.assert_not_called()
    logs.delete_log_group.assert_not_called()


def test_prefix_match_cannot_change_retention_of_another_runtime():
    logs = Mock()
    logs.describe_log_groups.return_value = {"logGroups": [{"logGroupName": GROUP + "-other"}]}
    with pytest.raises(TimeoutError):
        provision({"RequestType": "Create", "ResourceProperties": {"LogGroup": GROUP}}, logs, sleep=lambda _: None)
    logs.put_retention_policy.assert_not_called()


def test_stack_deletion_preserves_logs():
    logs = Mock()
    provision({"RequestType": "Delete", "ResourceProperties": {"LogGroup": GROUP}}, logs)
    assert not logs.mock_calls
