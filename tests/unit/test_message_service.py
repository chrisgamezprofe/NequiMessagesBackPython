from datetime import datetime, timezone

import pytest

from app.core.exceptions import DuplicateMessageError
from app.repositories.message_repository import MessageRepository
from app.schemas.message import MessageCreate, SenderType
from app.services.message_service import MessageService
from app.services.profanity_filter import ProfanityFilter


def _payload(**overrides) -> MessageCreate:
    fields = {
        "message_id": "msg-123456",
        "session_id": "session-abcdef",
        "content": "Hola, ¿cómo puedo ayudarte hoy?",
        "timestamp": datetime(2023, 6, 15, 14, 30, tzinfo=timezone.utc),
        "sender": SenderType.SYSTEM,
    }
    fields.update(overrides)
    return MessageCreate(**fields)


def test_process_and_store_computes_metadata(message_service: MessageService):
    result = message_service.process_and_store(_payload())

    assert result.message_id == "msg-123456"
    assert result.metadata.word_count == 5
    assert result.metadata.character_count == len("Hola, ¿cómo puedo ayudarte hoy?")
    assert result.metadata.contains_filtered_content is False


def test_process_and_store_censors_banned_words(message_service: MessageService):
    result = message_service.process_and_store(
        _payload(message_id="msg-2", content="eso fue una idiota decision")
    )

    assert "idiota" not in result.content
    assert result.metadata.contains_filtered_content is True
    assert result.original_content == "eso fue una idiota decision"


def test_process_and_store_rejects_duplicate_message_id(message_service: MessageService):
    message_service.process_and_store(_payload(message_id="dup-1"))

    with pytest.raises(DuplicateMessageError):
        message_service.process_and_store(_payload(message_id="dup-1"))


def test_get_session_messages_filters_and_paginates(message_service: MessageService):
    message_service.process_and_store(
        _payload(message_id="m1", session_id="s1", sender=SenderType.USER)
    )
    message_service.process_and_store(
        _payload(message_id="m2", session_id="s1", sender=SenderType.SYSTEM)
    )
    message_service.process_and_store(
        _payload(message_id="m3", session_id="s2", sender=SenderType.USER)
    )

    result = message_service.get_session_messages("s1", limit=20, offset=0, sender=None)
    assert result.pagination.total == 2

    filtered = message_service.get_session_messages("s1", limit=20, offset=0, sender="user")
    assert filtered.pagination.total == 1
    assert filtered.messages[0].message_id == "m1"


def test_get_session_messages_for_unknown_session_returns_empty_list(message_service: MessageService):
    result = message_service.get_session_messages("unknown", limit=20, offset=0, sender=None)

    assert result.messages == []
    assert result.pagination.total == 0


def test_search_messages_finds_by_content(message_service: MessageService):
    message_service.process_and_store(
        _payload(message_id="m1", content="el pago fue exitoso")
    )
    message_service.process_and_store(
        _payload(message_id="m2", content="hubo un error en la transacción")
    )

    result = message_service.search_messages("exitoso", limit=20, offset=0)

    assert result.pagination.total == 1
    assert result.messages[0].message_id == "m1"


class _SpyBroadcaster:
    def __init__(self) -> None:
        self.published: list = []

    def publish(self, message) -> None:
        self.published.append(message)


def test_process_and_store_works_without_a_broadcaster(
    repository: MessageRepository, profanity_filter: ProfanityFilter
):
    """El broadcaster es opcional (punto extra): sin él, el servicio funciona
    igual — simplemente nadie se entera en tiempo real por WebSocket."""
    service_without_broadcaster = MessageService(repository, profanity_filter)

    result = service_without_broadcaster.process_and_store(_payload())

    assert result.message_id == "msg-123456"


def test_process_and_store_publishes_to_broadcaster_when_present(
    repository: MessageRepository, profanity_filter: ProfanityFilter
):
    spy = _SpyBroadcaster()
    service_with_broadcaster = MessageService(repository, profanity_filter, broadcaster=spy)

    result = service_with_broadcaster.process_and_store(_payload())

    assert spy.published == [result]
