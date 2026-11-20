"""Service-to-service authentication (shared API key).

Trusted non-user callers (today: the RAW bot-worker, which POSTs a finished
assessment's transcript to the ingest endpoint) authenticate with a shared
secret in the ``X-Service-Key`` header, NOT a user bearer token — there is
no logged-in user behind a bot-worker shutdown callback.

Fails closed: if ``SERVICE_API_KEY`` is not configured, every call is
refused (503). A missing secret must never mean "no auth required".
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_service_key(x_service_key: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency: 503 if the key isn't configured, 401 if it's
    missing or wrong. Constant-time compare to avoid leaking the secret
    byte-by-byte via timing."""
    configured = get_settings().SERVICE_API_KEY
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service auth is not configured (SERVICE_API_KEY unset).",
        )
    if not x_service_key or not hmac.compare_digest(x_service_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Service-Key.",
        )
