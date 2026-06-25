"""Cached Temporal client + graceful availability checks.

`get_temporal_client()` raises `AppError(503)` — not a raw exception —
when either the `temporalio` extra isn't installed or the server is
unreachable. Callers (the workflow service / API) surface that as a clean
503 so the rest of the app keeps working without Temporal.
"""

import logging
from typing import Optional

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.temporal.compat import TEMPORAL_AVAILABLE, Client

log = logging.getLogger(__name__)

_client: Optional[object] = None


class TemporalUnavailableError(AppError):
    status_code = 503
    error_code = "temporal_unavailable"


async def get_temporal_client():
    """Return the cached client, connecting on first use.

    Raises TemporalUnavailableError (503) if the SDK is missing or the
    server can't be reached within the connect timeout.
    """
    global _client
    if not TEMPORAL_AVAILABLE:
        raise TemporalUnavailableError(
            "Durable workflows are unavailable — the 'temporalio' extra is not installed."
        )
    if _client is not None:
        return _client

    settings = get_settings()
    try:
        _client = await Client.connect(  # type: ignore[union-attr]
            settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
        )
    except Exception as exc:  # noqa: BLE001 — any connect failure → clean 503
        log.warning("Temporal connect failed (%s): %s", settings.TEMPORAL_HOST, exc)
        raise TemporalUnavailableError(
            f"Could not reach the Temporal server at {settings.TEMPORAL_HOST}."
        ) from exc

    log.info("Temporal client connected to %s", settings.TEMPORAL_HOST)
    return _client


async def close_temporal_client() -> None:
    global _client
    _client = None
