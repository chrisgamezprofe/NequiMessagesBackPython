from fastapi.testclient import TestClient

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


def test_health_check(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_message_returns_201_with_processed_metadata(client: TestClient):
    response = client.post("/api/v1/messages", json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["message_id"] == "msg-123456"
    assert body["data"]["metadata"]["word_count"] == 5
    assert body["data"]["metadata"]["contains_filtered_content"] is False
    assert "processed_at" in body["data"]["metadata"]


def test_create_message_censors_inappropriate_content(client: TestClient):
    response = client.post(
        "/api/v1/messages",
        json=_payload(message_id="msg-bad", content="eso fue una idiota decision"),
    )

    assert response.status_code == 201
    body = response.json()
    assert "idiota" not in body["data"]["content"]
    assert body["data"]["metadata"]["contains_filtered_content"] is True
    # El filtrado nunca destruye el original: solo lo oculta en `content`.
    assert body["data"]["original_content"] == "eso fue una idiota decision"


def test_create_message_rejects_invalid_sender(client: TestClient):
    response = client.post("/api/v1/messages", json=_payload(sender="admin"))

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_FORMAT"


def test_create_message_rejects_missing_required_field(client: TestClient):
    payload = _payload()
    del payload["content"]

    response = client.post("/api/v1/messages", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FORMAT"


def test_create_message_rejects_invalid_timestamp(client: TestClient):
    response = client.post("/api/v1/messages", json=_payload(timestamp="not-a-date"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FORMAT"


def test_create_message_rejects_duplicate_message_id(client: TestClient):
    client.post("/api/v1/messages", json=_payload(message_id="dup-1"))
    response = client.post("/api/v1/messages", json=_payload(message_id="dup-1"))

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "DUPLICATE_MESSAGE_ID"


def test_get_messages_by_session_returns_created_messages(client: TestClient):
    client.post("/api/v1/messages", json=_payload(message_id="m1", session_id="s1"))
    client.post("/api/v1/messages", json=_payload(message_id="m2", session_id="s1"))
    client.post("/api/v1/messages", json=_payload(message_id="m3", session_id="s2"))

    response = client.get("/api/v1/messages/s1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["pagination"]["total"] == 2
    assert {m["message_id"] for m in body["data"]["messages"]} == {"m1", "m2"}


def test_get_messages_by_session_supports_pagination(client: TestClient):
    for i in range(5):
        client.post(
            "/api/v1/messages",
            json=_payload(message_id=f"m{i}", session_id="s1", timestamp=f"2023-06-15T14:3{i}:00Z"),
        )

    # order=asc explícito: esta prueba valida paginación, no el orden por
    # defecto (que tiene sus propios tests más abajo).
    response = client.get("/api/v1/messages/s1", params={"limit": 2, "offset": 2, "order": "asc"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["pagination"] == {"limit": 2, "offset": 2, "total": 5}
    assert [m["message_id"] for m in body["data"]["messages"]] == ["m2", "m3"]


def test_get_messages_by_session_orders_by_most_recent_first_by_default(client: TestClient):
    for i in range(3):
        client.post(
            "/api/v1/messages",
            json=_payload(message_id=f"m{i}", session_id="s1", timestamp=f"2023-06-15T14:3{i}:00Z"),
        )

    response = client.get("/api/v1/messages/s1")

    assert response.status_code == 200
    body = response.json()
    assert [m["message_id"] for m in body["data"]["messages"]] == ["m2", "m1", "m0"]


def test_get_messages_by_session_can_request_ascending_order(client: TestClient):
    for i in range(3):
        client.post(
            "/api/v1/messages",
            json=_payload(message_id=f"m{i}", session_id="s1", timestamp=f"2023-06-15T14:3{i}:00Z"),
        )

    response = client.get("/api/v1/messages/s1", params={"order": "asc"})

    assert response.status_code == 200
    body = response.json()
    assert [m["message_id"] for m in body["data"]["messages"]] == ["m0", "m1", "m2"]


def test_get_messages_by_session_rejects_invalid_order(client: TestClient):
    response = client.get("/api/v1/messages/s1", params={"order": "sideways"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FORMAT"


def test_get_messages_by_session_filters_by_sender(client: TestClient):
    client.post("/api/v1/messages", json=_payload(message_id="m1", session_id="s1", sender="user"))
    client.post("/api/v1/messages", json=_payload(message_id="m2", session_id="s1", sender="system"))

    response = client.get("/api/v1/messages/s1", params={"sender": "user"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["pagination"]["total"] == 1
    assert body["data"]["messages"][0]["message_id"] == "m1"


def test_get_messages_by_session_rejects_invalid_sender_filter(client: TestClient):
    response = client.get("/api/v1/messages/s1", params={"sender": "invalid"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FORMAT"


def test_get_messages_for_unknown_session_returns_empty_list(client: TestClient):
    response = client.get("/api/v1/messages/does-not-exist")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["messages"] == []
    assert body["data"]["pagination"]["total"] == 0


def test_search_messages_finds_by_content(client: TestClient):
    client.post("/api/v1/messages", json=_payload(message_id="m1", content="el pago fue exitoso"))
    client.post("/api/v1/messages", json=_payload(message_id="m2", content="hubo un error"))

    response = client.get("/api/v1/messages/search", params={"q": "exitoso"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["pagination"]["total"] == 1
    assert body["data"]["messages"][0]["message_id"] == "m1"


def test_search_messages_requires_query_param(client: TestClient):
    response = client.get("/api/v1/messages/search")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_FORMAT"


def test_search_messages_finds_by_a_word_that_was_censored(client: TestClient):
    """Reproduce el caso reportado: crear un mensaje con una palabra prohibida
    y luego buscarlo por esa misma palabra debe encontrarlo, aunque en
    `content` ya no aparezca (quedó censurada)."""
    client.post(
        "/api/v1/messages",
        json=_payload(message_id="m1", content="eso fue una idiota decision"),
    )

    response = client.get("/api/v1/messages/search", params={"q": "idiota"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["pagination"]["total"] == 1
    found = body["data"]["messages"][0]
    assert found["message_id"] == "m1"
    assert "idiota" not in found["content"]
    assert found["original_content"] == "eso fue una idiota decision"


def test_rate_limit_returns_429_after_exceeding_window(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'rate-limit-test.db'}"
    app = create_app(database_url=db_url, rate_limit_requests=2, rate_limit_window_seconds=60)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        third = client.get("/health")

    assert third.status_code == 429
    assert third.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
