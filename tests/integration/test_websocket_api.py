"""Pruebas de integración del WebSocket (punto extra opcional)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app


def _payload(**overrides) -> dict:
    payload = {
        "message_id": "msg-123456",
        "session_id": "session-abcdef",
        "content": "Hola, ¿cómo puedo ayudarte hoy?",
        "timestamp": "2023-06-15T14:30:00Z",
        "sender": "system",
    }
    payload.update(overrides)
    return payload


def test_websocket_receives_new_message_for_its_session(client: TestClient):
    with client.websocket_connect("/ws/messages/session-ws-1") as websocket:
        response = client.post(
            "/api/v1/messages", json=_payload(message_id="ws-1", session_id="session-ws-1")
        )
        assert response.status_code == 201

        received = websocket.receive_json()

    assert received["message_id"] == "ws-1"
    assert received["session_id"] == "session-ws-1"


def test_websocket_does_not_receive_messages_from_other_sessions(client: TestClient):
    with client.websocket_connect("/ws/messages/session-ws-2") as websocket:
        client.post("/api/v1/messages", json=_payload(message_id="ws-2", session_id="other-session"))
        client.post("/api/v1/messages", json=_payload(message_id="ws-3", session_id="session-ws-2"))

        received = websocket.receive_json()

    assert received["message_id"] == "ws-3"


def test_websocket_shows_censored_content_not_the_original(client: TestClient):
    with client.websocket_connect("/ws/messages/session-ws-3") as websocket:
        client.post(
            "/api/v1/messages",
            json=_payload(
                message_id="ws-4",
                session_id="session-ws-3",
                content="eso fue una idiota decision",
            ),
        )

        received = websocket.receive_json()

    assert "idiota" not in received["content"]
    assert received["original_content"] == "eso fue una idiota decision"


def test_websocket_rejects_invalid_api_key_when_auth_enabled(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ws-auth-test.db'}"
    app = create_app(database_url=db_url, rate_limit_requests=1000, api_key="secret-key")

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/messages/session-1?api_key=wrong-key"):
                pass

    assert exc_info.value.code == 4401


def test_websocket_accepts_correct_api_key_when_auth_enabled(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ws-auth-test.db'}"
    app = create_app(database_url=db_url, rate_limit_requests=1000, api_key="secret-key")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/messages/session-1?api_key=secret-key") as websocket:
            response = client.post(
                "/api/v1/messages",
                json=_payload(message_id="ws-auth-1", session_id="session-1"),
                headers={"X-API-Key": "secret-key"},
            )
            assert response.status_code == 201

            received = websocket.receive_json()

    assert received["message_id"] == "ws-auth-1"
