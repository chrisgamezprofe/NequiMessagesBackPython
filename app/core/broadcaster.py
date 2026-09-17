"""Eventos que notifica mensajes nuevos a clientes WebSocket
suscritos a una sesión.

Limitación: vive en memoria
de un solo proceso, así que no sirve tal cual para un despliegue con varias
réplicas sin un backend de pub/sub compartido (Redis, etc.).
"""
import asyncio
from collections import defaultdict

from app.schemas.message import MessageResponse


class MessageBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[MessageResponse]]] = defaultdict(set)

    def subscribe(self, session_id: str) -> asyncio.Queue[MessageResponse]:
        channel: asyncio.Queue[MessageResponse] = asyncio.Queue()
        self._subscribers[session_id].add(channel)
        return channel

    def unsubscribe(self, session_id: str, channel: asyncio.Queue[MessageResponse]) -> None:
        self._subscribers[session_id].discard(channel)
        if not self._subscribers[session_id]:
            del self._subscribers[session_id]

    def publish(self, message: MessageResponse) -> None:
        for channel in list(self._subscribers.get(message.session_id, ())):
            channel.put_nowait(message)
