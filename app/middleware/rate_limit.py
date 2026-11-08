"""Simple in-process sliding window rate limiter middleware."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 120, burst: int = 60):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.burst = burst
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        # Paths that are more sensitive
        self._sensitive = (
            "/api/auth",
            "/api/companies/me/credits",
            "/api/ai-search",
            "/api/admin",
        )

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip OPTIONS
        if request.method == "OPTIONS":
            return await call_next(request)
        client = request.client.host if request.client else "anonymous"
        key = f"{client}:{request.url.path}"
        now = time.time()
        window = self._windows[key]
        # Remove old entries (older than 60s)
        while window and now - window[0] > 60:
            window.popleft()
        # Apply stricter limits to sensitive paths
        limit = self.rpm
        path = request.url.path
        if any(path.startswith(s) for s in self._sensitive):
            limit = min(self.rpm, 60)  # stricter
        if len(window) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests", "code": "rate_limited"},
                headers={"Retry-After": "60"},
            )
        window.append(now)
        response = await call_next(request)
        return response
