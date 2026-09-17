import pytest

from app.core.api_key_auth import build_api_key_dependency, is_valid_api_key
from app.core.exceptions import InvalidApiKeyError


def test_is_valid_api_key_true_when_auth_disabled():
    assert is_valid_api_key(provided=None, expected_key=None) is True
    assert is_valid_api_key(provided="anything", expected_key=None) is True


def test_is_valid_api_key_requires_exact_match_when_enabled():
    assert is_valid_api_key(provided="secret", expected_key="secret") is True
    assert is_valid_api_key(provided="wrong", expected_key="secret") is False
    assert is_valid_api_key(provided=None, expected_key="secret") is False


def test_require_api_key_dependency_allows_request_when_disabled():
    dependency = build_api_key_dependency(expected_key=None)

    dependency(x_api_key=None)  # no debe lanzar


def test_require_api_key_dependency_raises_when_missing():
    dependency = build_api_key_dependency(expected_key="secret")

    with pytest.raises(InvalidApiKeyError):
        dependency(x_api_key=None)


def test_require_api_key_dependency_raises_when_wrong():
    dependency = build_api_key_dependency(expected_key="secret")

    with pytest.raises(InvalidApiKeyError):
        dependency(x_api_key="wrong")


def test_require_api_key_dependency_allows_when_correct():
    dependency = build_api_key_dependency(expected_key="secret")

    dependency(x_api_key="secret")  # no debe lanzar
