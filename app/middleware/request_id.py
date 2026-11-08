"""Per-request correlation id.

Injects a UUID-shaped id into a ContextVar so log lines emitted during
the request lifecycle are correlatable (see `app.core.logging`). If the
caller already supplies `X-Request-ID` we echo it back, which simplifies
end-to-end tracing across frontend + backend logs.

Implemented as raw ASGI middleware rather than `BaseHTTPMiddleware` (M4) —
same behavior (set the ContextVar, always overwrite the response header via
the `http.response.start` message) without the extra task + memory stream.
"""

import uuid

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

_HEADER = "X-Request-ID"
_HEADER_BYTES = _HEADER.lower().encode("latin-1")


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        req_id = Headers(scope=scope).get(_HEADER) or uuid.uuid4().hex[:12]
        token = request_id_var.set(req_id)

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Mirror `response.headers[...] = req_id`: replace any value
                # the app may have set (headers are lowercase on the wire).
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != _HEADER_BYTES
                ]
                headers.append((_HEADER_BYTES, req_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            request_id_var.reset(token)
