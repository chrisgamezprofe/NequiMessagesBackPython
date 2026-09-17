"""Fixtures compartidas. Cada test recibe una base de datos SQLite propia en un
archivo temporal (vía `tmp_path` de pytest), así que las pruebas no comparten estado
ni afectan la base de datos real del proyecto."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import Database
from app.main import create_app
from app.repositories.message_repository import MessageRepository
from app.services.message_service import MessageService
from app.services.profanity_filter import ProfanityFilter

TEST_BANNED_WORDS = {"idiota", "estupido", "gonorrea"}


@pytest.fixture()
def db_session(tmp_path) -> Session:
    database = Database(f"sqlite:///{tmp_path / 'unit-test.db'}")
    database.init_db()
    session = database.session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository(db_session: Session) -> MessageRepository:
    return MessageRepository(db_session)


@pytest.fixture()
def profanity_filter() -> ProfanityFilter:
    return ProfanityFilter(TEST_BANNED_WORDS)


@pytest.fixture()
def message_service(repository: MessageRepository, profanity_filter: ProfanityFilter) -> MessageService:
    return MessageService(repository, profanity_filter)


@pytest.fixture()
def app(tmp_path) -> FastAPI:
    db_url = f"sqlite:///{tmp_path / 'api-test.db'}"
    # Límite de rate limiting alto por defecto: las pruebas de la API no deben
    # verse afectadas salvo el test dedicado a rate limiting, que usa su propia app.
    return create_app(database_url=db_url, rate_limit_requests=1000, rate_limit_window_seconds=60)


@pytest.fixture()
def client(app: FastAPI):
    with TestClient(app) as test_client:
        yield test_client
