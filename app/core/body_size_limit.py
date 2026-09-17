"""Middleware que rechaza requests cuyo body declara ser más grande de lo
permitido, antes de que FastAPI/Pydantic lo lean completo en memoria.

Sin esto, un body de varios MB se lee entero aunque `MessageCreate.content`
(máx. 5000 caracteres) lo vaya a rechazar de todos modos: la validación de
Pydantic ocurre después de que Starlette ya cargó el body completo.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > self._max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "status": "error",
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": "El cuerpo de la solicitud excede el tamaño máximo permitido",
                        "details": f"Máximo {self._max_body_bytes} bytes",
                    },
                },
            )
        return await call_next(request)
