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

    async def dispatch(self, request: Request, call_next) -> Response:
        client_id = request.client.host if request.client else "unknown"
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
