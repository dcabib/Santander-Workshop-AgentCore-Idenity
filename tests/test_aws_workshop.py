from copy import deepcopy
from unittest.mock import Mock

import pytest

from santander_demo.aws_workshop.config import DOMAINS, check_accounts, stack_outputs, validate


@pytest.fixture
def config():
    return {
        "schema_version": 1,
        "project": "test-workshop",
        "region": "us-east-1",
        "auth_provider": "cognito",
        "source_kind": "aws_simulated_databricks",
        "accounts": {
            name: {"id": str(index + 1) * 12, "profile": name}
            for index, name in enumerate(DOMAINS)
        },
    }


def test_preflight_rejects_wrong_account_before_any_resource_call(config):
    aws = Mock()
    aws.client.return_value.get_caller_identity.return_value = {
        "Account": "999999999999", "Arn": "arn:aws:iam::999999999999:role/wrong"
    }
    with pytest.raises(ValueError, match="WRONG_AWS_ACCOUNT:platform"):
        check_accounts(config, session_factory=lambda *_: aws)
    aws.client.assert_called_once_with("sts")


def test_multi_account_preflight_cannot_pass_with_reused_account(config):
    config["accounts"]["retail-banking"]["id"] = config["accounts"]["platform"]["id"]
    factory = Mock()
    with pytest.raises(ValueError, match="DISTINCT_AWS_ACCOUNTS_REQUIRED"):
        check_accounts(config, domains=DOMAINS, session_factory=factory)
    factory.assert_not_called()


def test_missing_domain_credentials_dont_prevent_platform_work(config):
    config["accounts"]["transaction-banking"]["id"] = None
    aws = Mock()
    aws.client.return_value.get_caller_identity.return_value = {
        "Account": "111111111111", "Arn": "arn:aws:iam::111111111111:role/operator"
    }
    result = check_accounts(config, session_factory=lambda *_: aws)
    assert set(result) == {"platform"}
    with pytest.raises(ValueError, match="WORKSHOP_ACCOUNT_ID_REQUIRED"):
        check_accounts(config, domains=DOMAINS, session_factory=lambda *_: aws)


@pytest.mark.parametrize("field", ["password", "access_token", "client_secret", "aws_session_token"])
def test_configuration_rejects_embedded_secrets_at_any_depth(config, field):
    config["accounts"]["platform"]["extra"] = [{field: "must-not-be-persisted"}]
    with pytest.raises(ValueError, match="CONFIG_IDENTIFIERS_ONLY"):
        validate(config)


@pytest.mark.parametrize("key,value", [
    ("auth_provider", "local"),
    ("source_kind", "local"),
    ("source_kind", "databricks"),
])
def test_execution_kind_must_be_explicit_and_aws_hosted(config, key, value):
    bad = deepcopy(config)
    bad[key] = value
    with pytest.raises(ValueError):
        validate(bad)


def test_stack_rollback_cannot_count_as_ready():
    aws = Mock()
    aws.client.return_value.describe_stacks.return_value = {
        "Stacks": [{
            "StackStatus": "UPDATE_ROLLBACK_COMPLETE",
            "Outputs": [{"OutputKey": "GatewayUrl", "OutputValue": "stale"}],
        }]
    }
    with pytest.raises(RuntimeError, match="STACK_NOT_READY"):
        stack_outputs(aws, "exact-workshop-stack")
    aws.client.return_value.describe_stacks.assert_called_once_with(
        StackName="exact-workshop-stack"
    )
