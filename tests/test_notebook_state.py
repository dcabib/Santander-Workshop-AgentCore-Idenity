import json
from unittest.mock import patch

import pytest

from santander_demo.notebook_state import NotebookState


def state_at(path, account="123456789012", region="us-west-2"):
    return NotebookState(path, account_id=account, region=region)


def test_restart_preserves_identifiers_without_aws_or_configuration_file(tmp_path):
    state = state_at(tmp_path)
    state.record("gateway", {"id": "gw-123", "arn": "example"}, lesson="01")
    resumed = state_at(tmp_path)
    assert resumed.prefix == state.prefix
    assert resumed.tags == state.tags
    assert resumed.require("gateway", lesson="01")["id"] == "gw-123"


@pytest.mark.parametrize("key", [
    "SecretString", "ClientSecret", "AuthenticationResult",
    "aws_session_token", "Authorization",
])
def test_authentication_response_cannot_be_persisted(tmp_path, key):
    state = state_at(tmp_path)
    original = state.path.read_bytes()
    payload = (
        {key: {"AccessToken": "not-a-real-token"}}
        if key == "AuthenticationResult" else {key: "not-a-real-secret"}
    )
    with pytest.raises(ValueError, match="SECRETS_FORBIDDEN"):
        state.record("login", payload, lesson="02")
    assert state.path.read_bytes() == original
    assert state.get("login") is None


def test_another_account_cannot_adopt_a_copied_state(tmp_path):
    original = state_at(tmp_path)
    copied = tmp_path / "999999999999-us-west-2.json"
    copied.write_bytes(original.path.read_bytes())
    with pytest.raises(ValueError, match="CONTEXT_MISMATCH"):
        state_at(tmp_path, account="999999999999")


def test_resource_record_cannot_silently_replace_owned_identifier(tmp_path):
    state = state_at(tmp_path)
    state.record("gateway", {"id": "one"}, lesson="01")
    with pytest.raises(ValueError, match="ALREADY_RECORDED"):
        state.record("gateway", {"id": "two"}, lesson="01")
    assert state.require("gateway", lesson="01")["id"] == "one"


def test_failed_write_retains_previous_disk_and_memory_state(tmp_path):
    state = state_at(tmp_path)
    original = state.path.read_bytes()
    with patch("santander_demo.notebook_state.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            state.record("gateway", {"id": "one"}, lesson="01")
    assert state.path.read_bytes() == original
    assert state.get("gateway") is None
    assert list(tmp_path.iterdir()) == [state.path]


def test_cleanup_requires_the_exact_record_and_persists_removal(tmp_path):
    state = state_at(tmp_path)
    recorded = state.record("gateway", {"id": "one"}, lesson="01")
    with pytest.raises(ValueError, match="STATE_CHANGED"):
        state.forget("gateway", expected={"id": "different"})
    assert state.get("gateway") == recorded
    state.forget("gateway", expected=recorded)
    assert json.loads(state.path.read_text())["resources"] == {}
    with pytest.raises(RuntimeError, match="aula 01"):
        state.require("gateway", lesson="01")
