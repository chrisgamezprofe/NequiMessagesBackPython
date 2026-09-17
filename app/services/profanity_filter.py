"""Filtrado simple de palabras inapropiadas basado en una lista de palabras prohibidas.

Es intencionalmente simple y va en `services` porque es una
regla de negocio del flujo de procesamiento, no un detalle de persistencia.
"""
import re

_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


class ProfanityFilter:
    def __init__(self, banned_words: set[str] | None = None) -> None:
        self._banned_words = {word.lower() for word in (banned_words or set())}

    def contains_banned_word(self, text: str) -> bool:
        return any(token.lower() in self._banned_words for token in _TOKEN_PATTERN.findall(text))

    def censor(self, text: str) -> tuple[str, bool]:
        """Devuelve el texto censurado y si se encuentra contenido inapropiado."""
        found = False

        def _replace(match: re.Match[str]) -> str:
            nonlocal found
            word = match.group(0)
            if word.lower() in self._banned_words:
                found = True
                return "*" * len(word)
            return word

        censored = _TOKEN_PATTERN.sub(_replace, text)
        return censored, found
