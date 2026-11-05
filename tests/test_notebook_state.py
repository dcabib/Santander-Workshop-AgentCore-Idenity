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


def test_new_account_starts_empty_without_reusing_previous_account_ids(tmp_path):
    previous = state_at(tmp_path)
    previous.record("gateway", {"id": "previous-account-gateway"}, lesson="01")
    current = state_at(tmp_path, account="999999999999")
    assert current.data["resources"] == {}
    assert current.prefix != previous.prefix
    assert state_at(tmp_path).get("gateway")["id"] == "previous-account-gateway"


def test_cleanup_and_next_event_use_new_names_with_an_auditable_archive(tmp_path):
    state = state_at(tmp_path)
    entry = state.record("identity.demo_credentials", {"arn": "synthetic-secret-arn"}, lesson="01")
    with pytest.raises(RuntimeError, match="CLEANUP_INCOMPLETE"):
        state.complete_cleanup()
    with pytest.raises(RuntimeError, match="ACTIVE_EXECUTION"):
        state.start_new_execution()
    state.forget("identity.demo_credentials", expected=entry)
    state.complete_cleanup()
    resumed = state_at(tmp_path)
    assert resumed.is_closed
    with pytest.raises(RuntimeError, match="EXECUTION_CLOSED"):
        resumed.record("gateway", {"id": "another"}, lesson="01")
    old_prefix = resumed.prefix
    archive = resumed.start_new_execution()
    assert resumed.prefix != old_prefix
    assert not resumed.is_closed and resumed.data["resources"] == {}
    history = json.loads(archive.read_text())
    assert history["released_resources"]["identity.demo_credentials"] == entry
    assert history["status"] == "CLEANED"
    assert state_at(tmp_path).prefix == resumed.prefix
    assert archive.stat().st_mode & 0o777 == 0o600


def test_failed_new_execution_can_retry_without_losing_closed_history(tmp_path):
    state = state_at(tmp_path)
    state.complete_cleanup()
    old_prefix = state.prefix
    with patch("santander_demo.notebook_state.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            state.start_new_execution()
    assert state.is_closed and state.prefix == old_prefix
    assert state_at(tmp_path).is_closed
    state.start_new_execution()
    assert state.prefix != old_prefix
    assert len(list((tmp_path / "history").glob("*.json"))) == 1


def test_failed_cleanup_checkpoint_preserves_active_run(tmp_path):
    state = state_at(tmp_path)
    with patch("santander_demo.notebook_state.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError):
            state.complete_cleanup()
    assert not state.is_closed
    assert not state_at(tmp_path).is_closed
