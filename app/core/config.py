"""Configuración de la aplicación, cargada desde variables de entorno (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MensajesNequi – Message Processing API"
    app_version: str = "1.0.0"

    database_url: str = "sqlite:///./data/messages.db"

    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Autenticación básica por API key:
    # mientras no se configure. Activarla con la variable de entorno API_KEY.
    api_key: str | None = None

    banned_words: list[str] = [
        "idiota",
        "estupido",
        "estúpido",
        "maldito",
        "spamword",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
