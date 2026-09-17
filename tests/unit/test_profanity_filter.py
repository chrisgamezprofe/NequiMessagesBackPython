from app.services.profanity_filter import ProfanityFilter


def test_contains_banned_word_detects_case_insensitive():
    filt = ProfanityFilter({"malo"})
    assert filt.contains_banned_word("Eso fue muy MALO de tu parte") is True


def test_contains_banned_word_returns_false_for_clean_text():
    filt = ProfanityFilter({"malo"})
    assert filt.contains_banned_word("Hola, ¿cómo puedo ayudarte hoy?") is False


def test_censor_replaces_banned_word_with_asterisks_and_preserves_length():
    filt = ProfanityFilter({"malo"})
    censored, found = filt.censor("Eso fue muy malo")

    assert found is True
    assert censored == "Eso fue muy ****"


def test_censor_leaves_clean_text_untouched():
    filt = ProfanityFilter({"malo"})
    original = "Hola, ¿cómo puedo ayudarte hoy?"
    censored, found = filt.censor(original)

    assert found is False
    assert censored == original


def test_censor_with_empty_banned_word_set_never_flags_content():
    filt = ProfanityFilter()
    censored, found = filt.censor("cualquier contenido aquí")

    assert found is False
    assert censored == "cualquier contenido aquí"


def test_censor_matches_whole_words_only():
    filt = ProfanityFilter({"mal"})
    censored, found = filt.censor("maleta y malabar no son mal")

    assert found is True
    assert censored == "maleta y malabar no son ***"
