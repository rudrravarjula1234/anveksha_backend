"""Emit one access-log line per request.

Replaces uvicorn's built-in access log so it picks up our request_id and
respects structured formatting.

Implemented as raw ASGI middleware rather than `BaseHTTPMiddleware` (M4):
the base class runs the downstream app in a separate task and shuttles the
response through an anyio memory stream, which costs a task hop plus
buffering on every request for no benefit here. Timing, log lines, and
status capture are unchanged — the status is read off the
`http.response.start` message, which is when the old `call_next()` returned.
"""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("anveksha.access")


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        method = scope["method"]
        path = scope["path"]
        started = False

        async def _send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                elapsed_ms = (time.perf_counter() - start) * 1000
                log.info("%s %s %s %.1fms", method, path, message["status"], elapsed_ms)
                if elapsed_ms > 2000:
                    log.warning("SLOW %s %s %.1fms", method, path, elapsed_ms)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            # Only the pre-response-start failure is an "ERR" line: once the
            # status line is out, an exception surfaces mid-body to the
            # caller, exactly as it did with BaseHTTPMiddleware.
            if not started:
                elapsed_ms = (time.perf_counter() - start) * 1000
                log.exception("%s %s ERR %.1fms", method, path, elapsed_ms)
            raise
