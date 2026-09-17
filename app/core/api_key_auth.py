"""Autenticación simple por API key.

Deshabilitada cuando no hay una key configurada. Se activa configurando `API_KEY` en el entorno, o
pasando `api_key=...` a `create_app` (usado por los tests).

Vive en `core/` porque autenticar peticiones no es una regla de negocio del dominio de mensajes:
es un detalle transversal de cómo se expone la API, igual que el rate limiting.
"""
from collections.abc import Callable

from fastapi import Header

from app.core.exceptions import InvalidApiKeyError


def is_valid_api_key(provided: str | None, expected_key: str | None) -> bool:
    """`expected_key is None` significa "autenticación deshabilitada": todo es
    válido. Si hay una key configurada, debe coincidir exactamente."""
    if expected_key is None:
        return True
    return provided == expected_key


def build_api_key_dependency(expected_key: str | None) -> Callable[..., None]:
    """Fábrica de la dependencia de FastAPI para rutas HTTP normales.

    Es una fábrica (no una función suelta) para que cada `create_app()`
    pueda fijar su propia `expected_key` sin depender de un singleton
    cacheado — el mismo patrón que ya usa `create_app` para
    `database_url` y los límites de rate limiting, para que los tests queden
    aislados entre sí.
    """

    def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
        if not is_valid_api_key(x_api_key, expected_key):
            raise InvalidApiKeyError(
                message="API key inválida o faltante",
                details="Incluye el header 'X-API-Key' con un valor válido",
            )

    return require_api_key
