"""Modelo ORM (SQLAlchemy) de un mensaje procesado.

`timestamp` y `processed_at` se guardan como texto ISO-8601 (UTC) en lugar de
`DateTime` nativo: SQLite no preserva zona horaria en columnas `DateTime`.
Guardaremos el ISO-8601 ya normalizado para evitar ese problema y sigue
siendo útil para ordenar, pero lo veremos al guardar.
"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MessageModel(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    original_content: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[str] = mapped_column(String, index=True, nullable=False)
    sender: Mapped[str] = mapped_column(String, index=True, nullable=False)

    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    contains_filtered_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[str] = mapped_column(String, nullable=False)
