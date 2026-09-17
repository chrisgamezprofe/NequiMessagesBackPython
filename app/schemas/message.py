"""Esquemas Pydantic: contrato de entrada/salida de la API, independiente del ORM."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SenderType(str, Enum):
    USER = "user"
    SYSTEM = "system"


class MessageCreate(BaseModel):
    """Quí ponemos lo que acepta el body vía `POST /api/messages`."""

    message_id: str = Field(..., min_length=1, max_length=100)
    session_id: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=5000)
    timestamp: datetime
    sender: SenderType

    @field_validator("message_id", "session_id", "content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("no puede estar vacío ni contener solo espacios en blanco")
        return value


class MessageMetadata(BaseModel):
    word_count: int
    character_count: int
    processed_at: datetime
    contains_filtered_content: bool = Field(
        description="True si se censuró contenido inapropiado en el mensaje original"
    )


class MessageResponse(BaseModel):
    """Representación de un mensaje ya procesado y almacenado.

    `content` es la versión segura de mostrar (con las palabras prohibidas
    censuradas). `original_content` conserva el texto tal como se recibió —el
    filtrado nunca destruye el dato original, solo lo oculta visualmente en
    `content`— útil para auditoría o para un panel de moderación que sí
    necesite ver qué se escribió realmente.
    """

    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    content: str
    original_content: str
    timestamp: datetime
    sender: SenderType
    metadata: MessageMetadata


class PaginationInfo(BaseModel):
    limit: int
    offset: int
    total: int


class MessageListData(BaseModel):
    messages: list[MessageResponse]
    pagination: PaginationInfo


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: str | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: ErrorDetail
