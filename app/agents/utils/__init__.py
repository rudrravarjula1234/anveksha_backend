"""Utility functions for the Agent Service.

Port note: the legacy ``utils/__init__.py`` also hosted
``AgentServiceSettings`` / ``get_encryption()`` (its own pydantic-settings
instance reading ``CREDENTIAL_ENCRYPTION_KEY`` from a hand-located ``.env``).
In this port those moved to :mod:`app.agents.credentials`, which uses the
application-wide :func:`app.core.config.get_settings` instead.
"""

from .retry import (
    DEFAULT_RETRY_CONFIG,
    RetryConfig,
    is_rate_limit_error,
    retry_with_exponential_backoff,
    with_retry,
)

__all__ = [
    "retry_with_exponential_backoff",
    "with_retry",
    "is_rate_limit_error",
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",
]
