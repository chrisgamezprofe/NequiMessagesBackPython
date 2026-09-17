"""Pruebas de integración de la autenticación por API key .
El fixture `client` de `tests/conftest.py` usa `create_app()` sin
`api_key`, así que la autenticación queda deshabilitada allí — estas pruebas
levantan su propia app con `api_key` configurado."""
from fastapi.testclient import TestClient

from app.main import create_app


def _payload(**overrides) -> dict:
    payload = {
        "message_id": "msg-1",
        "session_id": "session-1",
        "content": "hola",
        "timestamp": "2023-06-15T14:30:00Z",
        "sender": "user",
    }
    payload.update(overrides)
    return payload


def _client_with_auth(tmp_path, api_key: str = "secret-key") -> TestClient:
    db_url = f"sqlite:///{tmp_path / 'auth-test.db'}"
    app = create_app(database_url=db_url, rate_limit_requests=1000, api_key=api_key)
    return TestClient(app)


def test_requests_without_api_key_are_rejected_when_configured(tmp_path):
    with _client_with_auth(tmp_path) as client:
        response = client.post("/api/messages", json=_payload())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_API_KEY"


def test_requests_with_wrong_api_key_are_rejected(tmp_path):
    with _client_with_auth(tmp_path) as client:
        response = client.post(
            "/api/messages", json=_payload(), headers={"X-API-Key": "wrong-key"}
        )

    assert response.status_code == 401


def test_requests_with_correct_api_key_are_accepted(tmp_path):
    with _client_with_auth(tmp_path) as client:
        response = client.post(
            "/api/messages", json=_payload(), headers={"X-API-Key": "secret-key"}
        )

    assert response.status_code == 201


def test_get_and_search_endpoints_also_require_api_key(tmp_path):
    with _client_with_auth(tmp_path) as client:
        get_response = client.get("/api/messages/session-1")
        search_response = client.get("/api/messages/search", params={"q": "hola"})

    assert get_response.status_code == 401
    assert search_response.status_code == 401


def test_health_check_does_not_require_api_key(tmp_path):
    with _client_with_auth(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_auth_disabled_by_default(client: TestClient):
    response = client.post("/api/messages", json=_payload())

    assert response.status_code == 201
