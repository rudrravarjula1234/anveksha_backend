"""Application-level exception types and global handlers.

`AppError` is the only exception services / repositories should raise for
known failure conditions (not-found, validation rejection, conflict, etc.).
The handler in `main.py` translates them into clean JSON responses.

Unhandled exceptions are surfaced as 500s; the traceback is logged but
never returned to the client in production (DEBUG=true relaxes that).
"""

from typing import Any


class AppError(Exception):
    """Base for domain errors. Includes an HTTP status hint."""

    status_code: int = 400
    error_code: str = "app_error"

    def __init__(self, detail: str, *, status_code: int | None = None, extra: dict[str, Any] | None = None):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        self.extra = extra or {}


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"


class UnauthorizedError(AppError):
    status_code = 401
    error_code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    error_code = "forbidden"
