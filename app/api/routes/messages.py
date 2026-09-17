"""Controladores HTTP (capa de presentación): parsean la request, delegan en
`MessageService` y envuelven la respuesta en `{"status", "data"}` acordado.
No contiene lógica de negocio."""
from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.dependencies import get_message_service
from app.schemas.message import MessageCreate, OrderDirection, SenderType
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


def _success(data, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "success", "data": jsonable_encoder(data)})


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Recibe, valida, procesa y almacena un mensaje de chat",
)
async def create_message(
    payload: MessageCreate,
    service: MessageService = Depends(get_message_service),
) -> JSONResponse:
    # `async def` para correr en el event loop de asyncio.Queue y no colgar la app.
    result = service.process_and_store(payload)
    return _success(result, status.HTTP_201_CREATED)


@router.get(
    "/search",
    summary="Busca mensajes cuyo contenido incluya el texto dado",
)
def search_messages(
    q: str = Query(..., min_length=1, description="Texto a buscar dentro del contenido del mensaje"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de resultados"),
    offset: int = Query(0, ge=0, description="Cantidad de resultados a omitir"),
    service: MessageService = Depends(get_message_service),
) -> JSONResponse:
    result = service.search_messages(q, limit, offset)
    return _success(result)


@router.get(
    "/{session_id}",
    summary="Lista los mensajes de una sesión, con paginación y filtro por remitente",
)
def get_messages_by_session(
    session_id: str,
    limit: int = Query(20, ge=1, le=100, description="Cantidad máxima de resultados"),
    offset: int = Query(0, ge=0, description="Cantidad de resultados a omitir"),
    sender: SenderType | None = Query(None, description="Filtrar por remitente: 'user' o 'system'"),
    order: OrderDirection = Query(
        OrderDirection.DESC,
        description=(
            "Orden por fecha de envío (`timestamp`): 'desc' (default) muestra el último "
            "mensaje enviado primero; 'asc' muestra el más antiguo primero."
        ),
    ),
    service: MessageService = Depends(get_message_service),
) -> JSONResponse:
    result = service.get_session_messages(
        session_id, limit, offset, sender.value if sender else None, order.value
    )
    return _success(result)