"""Retry utilities with exponential backoff for rate limiting.

Ported unchanged from ``backend/lib/agent_service/utils/retry.py``.
"""

import asyncio
import functools
import logging
from typing import Any, Callable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimitError(Exception):
    """Wrapper for rate limit errors"""

    pass


def is_rate_limit_error(error: Exception) -> bool:
    """
    Check if an exception is a rate limit error.

    Handles various provider error formats:
    - OpenAI: RateLimitError, status 429
    - Azure: status 429
    - Vertex AI: RESOURCE_EXHAUSTED
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Check error type name
    if "ratelimit" in error_type.lower():
        return True

    # Check error message content
    rate_limit_indicators = [
        "429",
        "rate limit",
        "rate_limit",
        "ratelimit",
        "resource_exhausted",
        "resource exhausted",
        "too many requests",
        "quota exceeded",
        "throttl",
    ]

    return any(indicator in error_str for indicator in rate_limit_indicators)


async def retry_with_exponential_backoff(
    func: Callable[..., Any],
    *args,
    max_retries: int = 2,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retry_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    **kwargs,
) -> Any:
    """
    Execute a function with exponential backoff retry on rate limit errors.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts (default: 2)
        initial_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        retry_exceptions: Optional tuple of exception types to retry on
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        The last exception if all retries are exhausted
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            # Check if this is a retryable error
            should_retry = False
            if retry_exceptions and isinstance(e, retry_exceptions):
                should_retry = True
            elif is_rate_limit_error(e):
                should_retry = True

            if not should_retry or attempt >= max_retries:
                raise

            # Calculate delay with exponential backoff
            delay = min(initial_delay * (exponential_base**attempt), max_delay)

            logger.warning(
                f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). "
                f"Retrying in {delay:.1f}s... Error: {type(e).__name__}"
            )

            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    if last_exception:
        raise last_exception


def with_retry(
    max_retries: int = 2,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
):
    """
    Decorator to add retry with exponential backoff to async functions.

    Usage:
        @with_retry(max_retries=3, initial_delay=2.0)
        async def call_api():
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_exponential_backoff(
                func,
                *args,
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                exponential_base=exponential_base,
                **kwargs,
            )

        return wrapper

    return decorator


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_retries: int = 2,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        enabled: bool = True,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.enabled = enabled

    @classmethod
    def from_dict(cls, config: dict) -> "RetryConfig":
        """Create RetryConfig from dictionary"""
        return cls(
            max_retries=config.get("max_retries", 2),
            initial_delay=config.get("initial_delay", 1.0),
            max_delay=config.get("max_delay", 60.0),
            exponential_base=config.get("exponential_base", 2.0),
            enabled=config.get("enabled", True),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "max_retries": self.max_retries,
            "initial_delay": self.initial_delay,
            "max_delay": self.max_delay,
            "exponential_base": self.exponential_base,
            "enabled": self.enabled,
        }


# Default retry configuration
DEFAULT_RETRY_CONFIG = RetryConfig()
