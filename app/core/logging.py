"""Structured logging configuration.

We use stdlib logging configured once at app startup. Adds a `request_id`
filter so every log line in a request lifecycle is correlatable.
"""

import logging
import sys
from contextvars import ContextVar

# Request-scoped context var populated by `RequestIDMiddleware`. Defaults
# to "-" so log lines outside a request still format cleanly.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    """Attach the current request_id (or '-') to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s — %(message)s"


def setup_logging(level: str = "info") -> None:
    """Configure root + uvicorn loggers idempotently.

    Call once during app startup. Safe to call multiple times (clears
    existing handlers first to avoid duplicate output under hot-reload).
    """
    numeric = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(RequestIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").handlers.clear()  # we emit our own
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
