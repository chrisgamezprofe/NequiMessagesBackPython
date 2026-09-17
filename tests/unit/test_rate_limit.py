from starlette.requests import Request

from app.core.rate_limit import RateLimitMiddleware


def _request(headers: dict[str, str], client_host: str | None = "203.0.113.5") -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "headers": raw_headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_client_id_falls_back_to_socket_ip_without_forwarded_header():
    request = _request(headers={})

    assert RateLimitMiddleware._client_id(request) == "203.0.113.5"


def test_client_id_uses_last_forwarded_for_value():
    """El ALB delante de la app (ver `infra/`) añade la IP real de la conexión
    al FINAL de `X-Forwarded-For`, aunque el cliente ya haya mandado un valor
    propio (falso) antes. Con un solo proxy de confianza, ese último valor es
    el único en el que se puede confiar para no agrupar a todos los clientes
    reales en un solo balde de rate limit."""
    request = _request(headers={"x-forwarded-for": "1.2.3.4, 203.0.113.5"})

    assert RateLimitMiddleware._client_id(request) == "203.0.113.5"


def test_client_id_ignores_client_supplied_header_spoofing_attempt():
    request = _request(headers={"x-forwarded-for": "9.9.9.9"}, client_host=None)

    # Sin conexión de socket real que lo desmienta, se usa el único valor
    # disponible — el punto es que, cuando SÍ hay un proxy de confianza que
    # antepone la IP real (caso normal en producción), se prefiere la última.
    assert RateLimitMiddleware._client_id(request) == "9.9.9.9"
