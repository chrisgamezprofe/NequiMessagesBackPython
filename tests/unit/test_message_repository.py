from app.repositories.message_repository import MessageRepository


def _create(repository: MessageRepository, **overrides):
    fields = {
        "message_id": "msg-1",
        "session_id": "session-1",
        "content": "hola mundo",
        "timestamp": "2023-06-15T14:30:00+00:00",
        "sender": "user",
        "word_count": 2,
        "character_count": 10,
        "contains_filtered_content": False,
        "processed_at": "2023-06-15T14:30:01+00:00",
    }
    # Por defecto `original_content` coincide con `content` (nada se censuró);
    # los tests que sí necesitan divergencia lo pasan explícito como override.
    fields["original_content"] = overrides.get("content", fields["content"])
    fields.update(overrides)
    return repository.create(**fields)


def test_exists_is_false_for_unknown_message_id(repository: MessageRepository):
    assert repository.exists("does-not-exist") is False


def test_create_and_exists(repository: MessageRepository):
    _create(repository, message_id="msg-1")

    assert repository.exists("msg-1") is True


def test_list_by_session_returns_only_matching_session(repository: MessageRepository):
    _create(repository, message_id="msg-1", session_id="session-a")
    _create(repository, message_id="msg-2", session_id="session-b")

    records, total = repository.list_by_session("session-a", limit=20, offset=0)

    assert total == 1
    assert [r.message_id for r in records] == ["msg-1"]


def test_list_by_session_filters_by_sender(repository: MessageRepository):
    _create(repository, message_id="msg-1", session_id="session-a", sender="user")
    _create(repository, message_id="msg-2", session_id="session-a", sender="system")

    records, total = repository.list_by_session("session-a", limit=20, offset=0, sender="system")

    assert total == 1
    assert records[0].message_id == "msg-2"


def test_list_by_session_paginates_with_limit_and_offset(repository: MessageRepository):
    for i in range(5):
        _create(
            repository,
            message_id=f"msg-{i}",
            session_id="session-a",
            timestamp=f"2023-06-15T14:3{i}:00+00:00",
        )

    # `order="asc"` explícito: esta prueba valida paginación, no el orden por
    # defecto (que tiene sus propios tests más abajo).
    page1, total = repository.list_by_session("session-a", limit=2, offset=0, order="asc")
    page2, _ = repository.list_by_session("session-a", limit=2, offset=2, order="asc")

    assert total == 5
    assert [r.message_id for r in page1] == ["msg-0", "msg-1"]
    assert [r.message_id for r in page2] == ["msg-2", "msg-3"]


def test_list_by_session_orders_descending_by_default(repository: MessageRepository):
    """El último mensaje enviado (por `timestamp`) debe listarse primero."""
    for i in range(3):
        _create(
            repository,
            message_id=f"msg-{i}",
            session_id="session-a",
            timestamp=f"2023-06-15T14:3{i}:00+00:00",
        )

    records, _total = repository.list_by_session("session-a", limit=20, offset=0)

    assert [r.message_id for r in records] == ["msg-2", "msg-1", "msg-0"]


def test_list_by_session_orders_ascending_when_requested(repository: MessageRepository):
    for i in range(3):
        _create(
            repository,
            message_id=f"msg-{i}",
            session_id="session-a",
            timestamp=f"2023-06-15T14:3{i}:00+00:00",
        )

    records, _total = repository.list_by_session("session-a", limit=20, offset=0, order="asc")

    assert [r.message_id for r in records] == ["msg-0", "msg-1", "msg-2"]


def test_list_by_session_returns_empty_for_unknown_session(repository: MessageRepository):
    records, total = repository.list_by_session("does-not-exist", limit=20, offset=0)

    assert records == []
    assert total == 0


def test_search_finds_messages_by_content_substring(repository: MessageRepository):
    _create(repository, message_id="msg-1", content="el clima está soleado hoy")
    _create(repository, message_id="msg-2", content="me gusta la lluvia")

    records, total = repository.search("soleado", limit=20, offset=0)

    assert total == 1
    assert records[0].message_id == "msg-1"


def test_search_is_case_insensitive(repository: MessageRepository):
    _create(repository, message_id="msg-1", content="Hola Mundo")

    records, total = repository.search("mundo", limit=20, offset=0)

    assert total == 1
    assert records[0].message_id == "msg-1"


def test_search_finds_messages_by_a_censored_word(repository: MessageRepository):
    """La palabra prohibida ya no existe en `content` (quedó reemplazada por
    asteriscos), así que buscarla solo tiene sentido si se busca sobre
    `original_content` — este es justo el caso que se reportó como roto."""
    _create(
        repository,
        message_id="msg-1",
        content="eso fue una ****** decision",
        original_content="eso fue una idiota decision",
        contains_filtered_content=True,
    )

    records, total = repository.search("idiota", limit=20, offset=0)

    assert total == 1
    assert records[0].message_id == "msg-1"
    # La respuesta sigue mostrando la versión censurada — buscar por la
    # palabra prohibida no la "destapa" en el resultado.
    assert "idiota" not in records[0].content
