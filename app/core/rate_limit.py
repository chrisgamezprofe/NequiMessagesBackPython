"""Rate limiting simple (por IP de cliente).
Es suficiente para el alcance de este proyecto.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _client_id(request: Request) -> str:
        """`request.client.host` deja de servir para identificar al cliente
        real detrás de un proxy de confianza (el ALB de la propuesta de IaC en
        `infra/`): ahí, todo el tráfico le llega a Fargate desde la IP interna
        del load balancer, así que sin esto el rate limit agruparía a todos
        los usuarios reales en un solo balde.

        Se usa el ÚLTIMO valor de `X-Forwarded-For` en vez del primero: un
        cliente puede mandar su propio header falsificado, pero el ALB
        (el único proxy delante de la app en esta arquitectura) siempre
        *añade* la IP real de la conexión que le llegó al final de la lista —
        es el único valor de ese header en el que se puede confiar con un solo
        proxy intermedio.
        """
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[-1].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        client_id = self._client_id(request)
        now = time.monotonic()
        window_start = now - self._window_seconds

        hits = self._hits[client_id]
        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= self._max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Demasiadas solicitudes, intenta de nuevo más tarde",
                        "details": (
                            f"Límite de {self._max_requests} solicitudes cada "
                            f"{self._window_seconds} segundos"
                        ),
                    },
                },
            )

        hits.append(now)
        return await call_next(request)
