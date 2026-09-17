"""Configuración de acceso a base de datos (SQLAlchemy) desacoplada del resto de la app.

`Database` se instancia por aplicación en lugar de usar un engine global, de modo que
los tests puedan crear una instancia aislada (SQLite en un archivo temporal) sin tocar
la base de datos "real" usada en desarrollo/producción.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args)
        self.session_factory = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def init_db(self) -> None:
        from app.models import message  # noqa: F401

        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()


_default_database: Database | None = None


def get_default_database() -> Database:
    global _default_database
    if _default_database is None:
        from app.core.config import get_settings

        _default_database = Database(get_settings().database_url)
    return _default_database


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI por defecto. `create_app` la sobreescribe cuando recibe
    un `database_url` propio (por ejemplo, en tests)."""
    yield from get_default_database().get_session()
