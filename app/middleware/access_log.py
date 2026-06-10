"""Emit one access-log line per request.

Replaces uvicorn's built-in access log so it picks up our request_id and
respects structured formatting.
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("anveksha.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.exception(
                "%s %s ERR %.1fms", request.method, request.url.path, elapsed_ms
            )
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        if elapsed_ms > 2000:
            log.warning(
                "SLOW %s %s %.1fms", request.method, request.url.path, elapsed_ms
            )
        return response
