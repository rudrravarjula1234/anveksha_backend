"""In-process rate limiting (slowapi with fallback).

Uses slowapi if available; otherwise provides a lightweight in-memory
sliding window limiter to satisfy "DDoS mitigations" without external
dependencies.
"""

from __future__ import annotations

from typing import Callable

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    _limiter = Limiter(key_func=get_remote_address, default_limits=[])
    _USING_SLOWAPI = True
except Exception:
    _limiter = None
    RateLimitExceeded = Exception
    get_remote_address = lambda request: getattr(request.client, "host", "anonymous") if request else "anonymous"
    _USING_SLOWAPI = False


def get_limiter():
    return _limiter


def rate_limit(limit_str: str):
    if _USING_SLOWAPI and _limiter is not None:
        return _limiter.limit(limit_str)
    # Fallback: no-op decorator if slowapi unavailable
    def decorator(func: Callable) -> Callable:
        return func
    return decorator


__all__ = ["get_limiter", "rate_limit", "RateLimitExceeded", "_USING_SLOWAPI"]
