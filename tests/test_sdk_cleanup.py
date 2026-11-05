"""Confirmação eventual do Secrets Manager sem repetir a exclusão."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from santander_demo.notebook_state import NotebookState
from scripts.sdk_notebook_lessons import build_cleanup
from tests.test_sdk_gateway import ACCOUNT, REGION


@pytest.mark.parametrize("already_scheduled", [False, True])
def test_cleanup_waits_for_secret_and_preserves_recovery_window(tmp_path, already_scheduled):
    state = NotebookState(tmp_path, account_id=ACCOUNT, region=REGION)
    entry = state.record("identity.demo_credentials", {"arn": "registered-secret"}, lesson="01")
    scheduled = {"DeletedDate": "aws-confirmed-date"}
    secrets = Mock()
    secrets.describe_secret.side_effect = [scheduled] if already_scheduled else [{}, {}, scheduled]
    cell = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "secrets.delete_secret(" in c.source)
    exec(cell, {
        "state": state, "secrets": secrets,
        "time": SimpleNamespace(monotonic=lambda: 1, sleep=Mock()),
    })
    if already_scheduled:
        secrets.delete_secret.assert_not_called()
    else:
        secrets.delete_secret.assert_called_once_with(SecretId=entry["arn"], RecoveryWindowInDays=7)
    assert state.is_closed and not state.data["resources"]
    assert state.data["released_resources"]["identity.demo_credentials"]["arn"] == entry["arn"]


def test_cleanup_timeout_keeps_secret_record_for_resume(tmp_path):
    state = NotebookState(tmp_path, account_id=ACCOUNT, region=REGION)
    entry = state.record("identity.demo_credentials", {"arn": "registered-secret"}, lesson="01")
    secrets = Mock()
    secrets.describe_secret.return_value = {}
    cell = next(c.source for c in build_cleanup().cells if c.cell_type == "code" and "secrets.delete_secret(" in c.source)
    with pytest.raises(TimeoutError, match="SECRET_DELETION_CONFIRMATION_TIMEOUT"):
        exec(cell, {
            "state": state, "secrets": secrets,
            "time": SimpleNamespace(monotonic=Mock(side_effect=[0, 61]), sleep=Mock()),
        })
    assert state.get("identity.demo_credentials") == entry
    assert not state.is_closed
    secrets.delete_secret.assert_called_once_with(SecretId=entry["arn"], RecoveryWindowInDays=7)
