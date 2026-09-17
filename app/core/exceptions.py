"""Excepciones de dominio/aplicación.

Cada excepción sabe su propio código HTTP y su código de error de negocio, de modo
que en `app.main` pueda traducirlas al error estándar
`{"status": "error", "error": {"code", "message", "details"}}` sin necesidad de un
`if/elif`.
"""


class AppError(Exception):
    status_code: int = 400
    code: str = "APP_ERROR"

    def __init__(self, message: str, details: str | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class InvalidMessageFormatError(AppError):
    status_code = 422
    code = "INVALID_FORMAT"


class DuplicateMessageError(AppError):
    status_code = 409
    code = "DUPLICATE_MESSAGE_ID"


class InvalidApiKeyError(AppError):
    status_code = 401
    code = "INVALID_API_KEY"
