from unittest.mock import Mock

import pytest

from scripts import terraform_deploy


@pytest.mark.parametrize("changed", ["account_id", "region", "project_name"])
def test_state_migration_rejects_a_different_environment(changed):
    config = {"expected_account_id": "123456789012", "region": "us-east-1", "project_name": "lab"}
    output = {"account_id": config["expected_account_id"], "region": "us-east-1", "project_name": "lab"}
    output[changed] = "different"
    with pytest.raises(RuntimeError, match="STATE_TARGET_MISMATCH"):
        terraform_deploy.state_matches(config, {"outputs": {"workshop": {"value": output}}})


@pytest.mark.parametrize("control", ["encryption", "versioning", "public"])
def test_state_backend_requires_bucket_controls(monkeypatch, control):
    from santander_demo.aws_workshop import config as workshop_config

    s3 = Mock()
    s3.get_bucket_encryption.return_value = {"ServerSideEncryptionConfiguration": {"Rules": [
        {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}},
    ]}}
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.get_public_access_block.return_value = {"PublicAccessBlockConfiguration": {
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
    }}
    if control == "encryption":
        s3.get_bucket_encryption.return_value["ServerSideEncryptionConfiguration"]["Rules"] = []
    elif control == "versioning":
        s3.get_bucket_versioning.return_value = {"Status": "Suspended"}
    else:
        s3.get_public_access_block.return_value["PublicAccessBlockConfiguration"]["BlockPublicPolicy"] = False
    aws = Mock()
    aws.client.return_value = s3
    monkeypatch.setattr(terraform_deploy.boto3, "Session", lambda **kwargs: aws)
    monkeypatch.setattr(workshop_config, "stack_outputs", lambda *args: {"ArtifactBucket": "owned"})
    config = {
        "expected_account_id": "123456789012", "region": "us-east-1", "project_name": "lab",
        "backend": {"stack": "test-core-bootstrap", "key": "terraform/state/lab.tfstate"},
    }
    with pytest.raises(ValueError, match="STATE_BUCKET"):
        terraform_deploy.backend_configuration(config)
