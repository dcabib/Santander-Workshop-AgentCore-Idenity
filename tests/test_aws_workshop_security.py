import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from santander_demo.aws_workshop.backend import Source
from santander_demo.aws_workshop.identity import actor, verify
from santander_demo.aws_workshop.seed import provision


@pytest.fixture
def identity():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = {"issuer": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test", "clients": ["supervisor"]}
    claims = {
        "iss": config["issuer"], "sub": "person-c", "aud": "supervisor", "token_use": "id",
        "email_verified": True, "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return key, config, claims


@pytest.mark.parametrize("change", [
    {"aud": "other-app"},
    {"iss": "https://attacker.example"},
    {"token_use": "access"},
    {"email_verified": False},
    {"exp": datetime.now(UTC) - timedelta(seconds=1)},
])
def test_backend_rejects_wrong_identity_boundary(identity, change):
    key, config, claims = identity
    token = jwt.encode({**claims, **change}, key, algorithm="RS256")
    with pytest.raises((jwt.InvalidTokenError, ValueError)):
        verify(token, config, key=key.public_key())


def test_backend_rejects_forged_signature(identity):
    key, config, claims = identity
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(claims, impostor, algorithm="RS256")
    with pytest.raises(jwt.InvalidSignatureError):
        verify(token, config, key=key.public_key())


def test_memory_revalidates_revoked_acl_without_recovering_cached_content():
    claims = {"iss": "pool", "sub": "a"}
    memory, table = Mock(), Mock()
    memory.list_events.return_value = {"events": [{"payload": [{
        "conversational": {"content": {"text": '{"table_reference":"riscos"}'}},
    }]}]}
    table.get_item.return_value = {"Item": {"allowed": False}}
    result = Source(table, memory, "memory-123").recall(claims, "session-0123456789")
    assert result["documents"] == []
    assert result["references_seen"] == 1
    table.get_item.assert_called_once_with(
        Key={"pk": "ACL#a", "sk": "riscos"}, ConsistentRead=True,
    )
    assert memory.list_events.call_args.kwargs["actorId"] == actor(claims)


def test_memory_actor_cannot_be_replaced_by_shared_session_id():
    memory, table = Mock(), Mock()
    memory.list_events.return_value = {"events": []}
    source = Source(table, memory, "memory-123")
    for user in ["a", "b"]:
        source.recall({"iss": "pool", "sub": user}, "same-session-0123456789")
    calls = memory.list_events.call_args_list
    assert calls[0].kwargs["actorId"] != calls[1].kwargs["actorId"]
    assert calls[0].kwargs["sessionId"] == calls[1].kwargs["sessionId"]


def test_source_denial_does_not_read_data_even_after_gateway_allows():
    table = Mock()
    table.get_item.return_value = {}
    with pytest.raises(PermissionError, match="SOURCE_PERMISSION_DENIED"):
        Source(table, Mock(), "memory").read({"sub": "person-d"}, "fraude")
    table.get_item.assert_called_once_with(
        Key={"pk": "ACL#person-d", "sk": "fraude"}, ConsistentRead=True,
    )


def test_restricted_application_cannot_reach_fraud_by_alternative_table_tool():
    table = Mock()
    source = Source(table, Mock(), "memory", restricted_client="riscos-app")
    with pytest.raises(PermissionError, match="SOURCE_APPLICATION_DENIED"):
        source.read({"sub": "person-c", "aud": "riscos-app"}, "fraude")
    table.get_item.assert_not_called()


def test_iac_grant_update_writes_explicit_denials_for_revocation():
    table = Mock()
    writer = Mock()
    table.batch_writer.return_value.__enter__ = Mock(return_value=writer)
    table.batch_writer.return_value.__exit__ = Mock(return_value=False)
    provision({
        "RequestType": "Update",
        "ResourceProperties": {"Users": {"a": "subject-a"}, "GrantsJson": json.dumps({"a": []})},
    }, table)
    acl = [x.kwargs["Item"] for x in writer.put_item.call_args_list if x.kwargs["Item"]["pk"].startswith("ACL#")]
    assert len(acl) == 3
    assert all(x["allowed"] is False for x in acl)
