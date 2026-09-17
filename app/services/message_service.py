"""Orquesta el flujo de procesamiento de mensajes: validar, filtrar, enriquecer,
almacenar, y las consultas de recuperación o búsqueda. No conoce HTTP ni SQL."""
from datetime import datetime, timezone

from app.core.broadcaster import MessageBroadcaster
from app.core.exceptions import DuplicateMessageError
from app.models.message import MessageModel
from app.repositories.message_repository import MessageRepository
from app.schemas.message import (
    MessageCreate,
    MessageListData,
    MessageMetadata,
    MessageResponse,
    PaginationInfo,
)
from app.services.profanity_filter import ProfanityFilter


class MessageService:
    def __init__(
        self,
        repository: MessageRepository,
        profanity_filter: ProfanityFilter,
        broadcaster: MessageBroadcaster | None = None,
    ) -> None:
        self._repository = repository
        self._filter = profanity_filter
        # Opcional (punto extra): sin broadcaster, el servicio funciona igual,
        # simplemente nadie se entera en tiempo real por WebSocket.
        self._broadcaster = broadcaster

    def process_and_store(self, payload: MessageCreate) -> MessageResponse:
        if self._repository.exists(payload.message_id):
            raise DuplicateMessageError(
                message="El mensaje ya existe",
                details=f"Ya existe un mensaje con message_id '{payload.message_id}'",
            )

        censored_content, contains_filtered = self._filter.censor(payload.content)
        processed_at = datetime.now(timezone.utc)

        record = self._repository.create(
            message_id=payload.message_id,
            session_id=payload.session_id,
            content=censored_content,
            original_content=payload.content,
            timestamp=payload.timestamp.isoformat(),
            sender=payload.sender.value,
            word_count=len(censored_content.split()),
            character_count=len(censored_content),
            contains_filtered_content=contains_filtered,
            processed_at=processed_at.isoformat(),
        )
        response = self._to_response(record)
        if self._broadcaster is not None:
            self._broadcaster.publish(response)
        return response

    def get_session_messages(
        self,
        session_id: str,
        limit: int,
        offset: int,
        sender: str | None,
    ) -> MessageListData:
        records, total = self._repository.list_by_session(session_id, limit, offset, sender)
        return MessageListData(
            messages=[self._to_response(r) for r in records],
            pagination=PaginationInfo(limit=limit, offset=offset, total=total),
        )

    def search_messages(self, query: str, limit: int, offset: int) -> MessageListData:
        records, total = self._repository.search(query, limit, offset)
        return MessageListData(
            messages=[self._to_response(r) for r in records],
            pagination=PaginationInfo(limit=limit, offset=offset, total=total),
        )

    @staticmethod
    def _to_response(record: MessageModel) -> MessageResponse:
        return MessageResponse(
            message_id=record.message_id,
            session_id=record.session_id,
            content=record.content,
            original_content=record.original_content,
            timestamp=record.timestamp,
            sender=record.sender,
            metadata=MessageMetadata(
                word_count=record.word_count,
                character_count=record.character_count,
                processed_at=record.processed_at,
                contains_filtered_content=record.contains_filtered_content,
            ),
        )
