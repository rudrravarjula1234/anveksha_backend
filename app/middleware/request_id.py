"""Per-request correlation id.

Injects a UUID-shaped id into a ContextVar so log lines emitted during
the request lifecycle are correlatable (see `app.core.logging`). If the
caller already supplies `X-Request-ID` we echo it back, which simplifies
end-to-end tracing across frontend + backend logs.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.logging import request_id_var

_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        req_id = request.headers.get(_HEADER) or uuid.uuid4().hex[:12]
        token = request_id_var.set(req_id)
        try:
            response = await call_next(request)
            response.headers[_HEADER] = req_id
            return response
        finally:
            request_id_var.reset(token)
