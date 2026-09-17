"""Inyección de dependencias para las rutas de FastAPI."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.broadcaster import MessageBroadcaster
from app.core.config import get_settings
from app.core.database import get_db
from app.repositories.message_repository import MessageRepository
from app.services.message_service import MessageService
from app.services.profanity_filter import ProfanityFilter


def get_profanity_filter() -> ProfanityFilter:
    settings = get_settings()
    return ProfanityFilter(set(settings.banned_words))


def get_message_repository(db: Session = Depends(get_db)) -> MessageRepository:
    return MessageRepository(db)


def get_broadcaster(request: Request) -> MessageBroadcaster:
    return request.app.state.broadcaster


def get_message_service(
    repository: MessageRepository = Depends(get_message_repository),
    profanity_filter: ProfanityFilter = Depends(get_profanity_filter),
    broadcaster: MessageBroadcaster = Depends(get_broadcaster),
) -> MessageService:
    return MessageService(repository, profanity_filter, broadcaster)
