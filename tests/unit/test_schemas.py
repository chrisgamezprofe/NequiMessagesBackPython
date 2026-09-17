from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.message import MessageCreate, SenderType


def _valid_payload(**overrides) -> dict:
    payload = {
        "message_id": "msg-1",
        "session_id": "session-1",
        "content": "Hola, ¿cómo puedo ayudarte hoy?",
        "timestamp": "2023-06-15T14:30:00Z",
        "sender": "system",
    }
    payload.update(overrides)
    return payload


def test_message_create_accepts_valid_payload():
    message = MessageCreate(**_valid_payload())

    assert message.sender == SenderType.SYSTEM
    assert message.timestamp == datetime(2023, 6, 15, 14, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("sender", ["admin", "bot", "", "USER"])
def test_message_create_rejects_invalid_sender(sender):
    with pytest.raises(ValidationError):
        MessageCreate(**_valid_payload(sender=sender))


@pytest.mark.parametrize("field", ["message_id", "session_id", "content"])
def test_message_create_rejects_blank_fields(field):
    with pytest.raises(ValidationError):
        MessageCreate(**_valid_payload(**{field: "   "}))


def test_message_create_rejects_missing_required_field():
    payload = _valid_payload()
    del payload["content"]

    with pytest.raises(ValidationError):
        MessageCreate(**payload)


def test_message_create_rejects_invalid_timestamp_format():
    with pytest.raises(ValidationError):
        MessageCreate(**_valid_payload(timestamp="not-a-date"))
