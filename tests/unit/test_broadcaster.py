from app.core.broadcaster import MessageBroadcaster
from app.schemas.message import MessageMetadata, MessageResponse, SenderType
from datetime import datetime, timezone


def _message(**overrides) -> MessageResponse:
    fields = dict(
        message_id="msg-1",
        session_id="session-1",
        content="hola",
        original_content="hola",
        timestamp=datetime(2023, 6, 15, 14, 30, tzinfo=timezone.utc),
        sender=SenderType.USER,
        metadata=MessageMetadata(
            word_count=1,
            character_count=4,
            processed_at=datetime(2023, 6, 15, 14, 30, 1, tzinfo=timezone.utc),
            contains_filtered_content=False,
        ),
    )
    fields.update(overrides)
    return MessageResponse(**fields)


async def test_subscriber_receives_published_message_for_its_session():
    broadcaster = MessageBroadcaster()
    channel = broadcaster.subscribe("session-1")

    broadcaster.publish(_message(session_id="session-1"))

    received = await channel.get()
    assert received.message_id == "msg-1"


async def test_subscriber_does_not_receive_messages_from_other_sessions():
    broadcaster = MessageBroadcaster()
    channel = broadcaster.subscribe("session-1")

    broadcaster.publish(_message(session_id="other-session"))

    assert channel.empty()


def test_unsubscribe_stops_further_delivery():
    broadcaster = MessageBroadcaster()
    channel = broadcaster.subscribe("session-1")

    broadcaster.unsubscribe("session-1", channel)
    broadcaster.publish(_message(session_id="session-1"))

    assert channel.empty()


def test_publish_with_no_subscribers_does_not_raise():
    broadcaster = MessageBroadcaster()

    broadcaster.publish(_message(session_id="nobody-is-listening"))
