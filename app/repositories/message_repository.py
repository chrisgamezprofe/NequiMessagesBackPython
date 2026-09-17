"""Capa de acceso a datos para mensajes. Único lugar del proyecto que conoce SQLAlchemy.

Aislar esto detrás de una clase con métodos de negocio (no genéricos `get`/`save`)
permite reemplazar SQLite por otra base de datos sin tocar `services` ni `api`.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.message import MessageModel


class MessageRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def exists(self, message_id: str) -> bool:
        return self._db.get(MessageModel, message_id) is not None

    def create(self, **fields) -> MessageModel:
        record = MessageModel(**fields)
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record

    def list_by_session(
        self,
        session_id: str,
        limit: int,
        offset: int,
        sender: str | None = None,
        order: str = "desc",
    ) -> tuple[list[MessageModel], int]:
        stmt = select(MessageModel).where(MessageModel.session_id == session_id)
        if sender:
            stmt = stmt.where(MessageModel.sender == sender)

        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        # Se ordena por `timestamp` (cuándo se envió) ver `OrderDirection`
        # en app/schemas/message.py para el porqué.
        timestamp_order = MessageModel.timestamp.desc() if order == "desc" else MessageModel.timestamp.asc()
        stmt = stmt.order_by(timestamp_order).limit(limit).offset(offset)
        records = list(self._db.scalars(stmt))
        return records, total

    def search(self, query: str, limit: int, offset: int) -> tuple[list[MessageModel], int]:
        # Se busca sobre `original_content` (el texto real, sin censurar), no sobre
        # `content` (la versión con asteriscos): si se buscara sobre `content`, una
        # palabra prohibida jamás podría encontrarse, porque ya no existe ahí —fue
        # reemplazada por "*"—. Buscar sobre el original permite, por ejemplo, que
        # moderación encuentre los mensajes que SÍ tuvieron contenido filtrado. La
        # respuesta que se devuelve sigue mostrando `content` censurado igual que
        # siempre: esto solo cambia qué texto se usa para decidir si hay match.
        #
        # `query` la escribe quien llama a la API, así que `%` y `_` (los
        # caracteres especiales de `LIKE`) se escapan antes de envolverla entre
        # `%...%`: si no se escaparan, buscar `q=%` haría match con *cualquier*
        # mensaje (fuga de todo el contenido a través de "buscar"), y `_` haría
        # match con cualquier carácter en esa posición.
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
        stmt = select(MessageModel).where(MessageModel.original_content.ilike(pattern, escape="\\"))

        total = self._db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

        stmt = stmt.order_by(MessageModel.timestamp.desc()).limit(limit).offset(offset)
        records = list(self._db.scalars(stmt))
        return records, total
