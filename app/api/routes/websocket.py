"""Endpoint WebSocket: notifica en tiempo real los
mensajes nuevos de una sesión. Vive en su propio router, sin el prefijo
`/api/messages`, porque el path final es
`/ws/messages/{session_id}` que es la convención de URL de WebSocket, no de REST.

La autenticación por API key se revisa aquí manualmente (vía query param, no
el header `X-API-Key` que usan las rutas REST) porque un cliente WebSocket de
navegador por seguridad."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from app.core.api_key_auth import is_valid_api_key
from app.core.broadcaster import MessageBroadcaster

router = APIRouter(tags=["websocket"])

_POLICY_VIOLATION_CLOSE_CODE = 4401  # rango 4000-4999: código de cierre definido por la app


@router.websocket("/ws/v1/messages/{session_id}")
async def watch_session_messages(websocket: WebSocket, session_id: str, api_key: str | None = None) -> None:
    if not is_valid_api_key(api_key, websocket.app.state.api_key):
        await websocket.close(code=_POLICY_VIOLATION_CLOSE_CODE, reason="API key inválida o faltante")
        return

    await websocket.accept()

    broadcaster: MessageBroadcaster = websocket.app.state.broadcaster
    channel = broadcaster.subscribe(session_id)

    # Se espera concurrentemente a "llegó un mensaje nuevo" y a "el cliente se
    # desconectó", porque este socket solo empuja datos: no hay otra forma de
    # notar una desconexión mientras no se reciba nada del cliente.
    disconnect_task = asyncio.ensure_future(websocket.receive())
    try:
        while True:
            next_message_task = asyncio.ensure_future(channel.get())
            done, _pending = await asyncio.wait(
                {disconnect_task, next_message_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if disconnect_task in done:
                next_message_task.cancel()
                break
            message = next_message_task.result()
            await websocket.send_json(jsonable_encoder(message))
    except WebSocketDisconnect:
        pass
    finally:
        disconnect_task.cancel()
        broadcaster.unsubscribe(session_id, channel)
