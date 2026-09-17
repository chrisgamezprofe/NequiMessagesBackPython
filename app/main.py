"""Punto de entrada de la aplicación: construye el `FastAPI`, registra
middlewares, routers y errores globales.

`create_app` acepta parámetros opcionales (`database_url`, límites de rate limiting)
para que los tests puedan levantar instancias completamente aisladas entre sí, sin
tocar la base de datos real ni compartir estado de rate limiting entre pruebas.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.messages import router as messages_router
from app.api.routes.websocket import router as websocket_router
from app.core.api_key_auth import build_api_key_dependency
from app.core.body_size_limit import BodySizeLimitMiddleware
from app.core.broadcaster import MessageBroadcaster
from app.core.config import get_settings
from app.core.database import Database, get_db
from app.core.exceptions import AppError
from app.core.rate_limit import RateLimitMiddleware


def create_app(
    database_url: str | None = None,
    rate_limit_requests: int | None = None,
    rate_limit_window_seconds: int | None = None,
    api_key: str | None = None,
    max_body_bytes: int | None = None,
) -> FastAPI:
    settings = get_settings()
    database = Database(database_url or settings.database_url)
    effective_api_key = api_key if api_key is not None else settings.api_key

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.init_db()
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "API RESTful para recibir, validar, procesar y consultar mensajes de un "
            "sistema de chat. Arquitectura limpia por capas (controladores / "
            "servicios / repositorios).."
        ),
        lifespan=lifespan,
    )
    app.state.database = database
    app.state.broadcaster = MessageBroadcaster()
    # Usado por el WebSocket, que valida la API key manualmente (vía query
    # param, no header) — ver app/api/routes/websocket.py.
    app.state.api_key = effective_api_key

    if database_url is not None:
        def _get_db():
            yield from database.get_session()

        app.dependency_overrides[get_db] = _get_db

    app.add_middleware(
        RateLimitMiddleware,
        max_requests=rate_limit_requests or settings.rate_limit_requests,
        window_seconds=rate_limit_window_seconds or settings.rate_limit_window_seconds,
    )
    # Se agrega después del rate limit para que corra antes en la cadena de
    # middlewares (Starlette los ejecuta en orden inverso al de registro):
    # así un body demasiado grande se rechaza sin siquiera contar contra el
    # límite de solicitudes del cliente.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=max_body_bytes or settings.max_body_bytes,
    )

    require_api_key = Depends(build_api_key_dependency(effective_api_key))
    # El WebSocket no lleva `dependencies=[require_api_key]`: valida la key
    # manualmente (vía query param, no header) dentro del propio handler.
    app.include_router(messages_router, dependencies=[require_api_key])
    app.include_router(websocket_router)

    @app.get("/health", tags=["health"], summary="Chequeo del servicio")
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(AppError)
    def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            },
        )

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first_error = errors[0] if errors else {}
        field = ".".join(str(part) for part in first_error.get("loc", []) if part not in ("body", "query"))
        message = first_error.get("msg", "valor inválido")
        details = f"Campo '{field}': {message}" if field else message

        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "error": {
                    "code": "INVALID_FORMAT",
                    "message": "Formato de mensaje inválido",
                    "details": details,
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "error": {"code": "HTTP_ERROR", "message": str(exc.detail), "details": None},
            },
        )

    @app.exception_handler(Exception)
    def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Ha ocurrido un error inesperado en el servidor",
                    "details": None,
                },
            },
        )

    return app


app = create_app()
