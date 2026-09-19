"""
Retry with exponential backoff + full jitter.
Classifies errors as retryable vs non-retryable.
"""
from __future__ import annotations
import asyncio
import random
import time
import logging
from typing import Callable, TypeVar, Any
from functools import wraps

log = logging.getLogger("empire.resilience.retry")

T = TypeVar("T")


class RetryableError(Exception):
    """Marker for errors that should trigger a retry."""


class NonRetryableError(Exception):
    """Marker for errors that should NOT be retried (fail fast)."""


# HTTP status codes that are retryable
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504, 529}
# HTTP status codes that should NOT be retried
NON_RETRYABLE_HTTP_CODES = {400, 401, 403, 404, 422}


def classify_http_error(status: int, headers: dict | None = None) -> type[Exception]:
    """Map an HTTP status to a retry class."""
    if status in RETRYABLE_HTTP_CODES:
        return RetryableError
    if status in NON_RETRYABLE_HTTP_CODES:
        return NonRetryableError
    # Default: retry (transient)
    return RetryableError


def retry_with_backoff(
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[BaseException], ...] = (RetryableError,),
):
    """
    Decorator: exponential backoff with full jitter, classified retries.

    Usage:
        @retry_with_backoff(max_attempts=4)
        def call_api(...):
            response = client.post(...)
            if response.status_code in (429, 500, 503):
                raise RetryableError(f"HTTP {response.status_code}")
            if response.status_code == 401:
                raise NonRetryableError("auth failed")
            return response.json()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except NonRetryableError:
                    raise
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        log.error(f"[{func.__name__}] exhausted retries: {e}")
                        raise
                    delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    if jitter:
                        delay = random.uniform(0, delay)
                    log.warning(
                        f"[{func.__name__}] attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
            if last_exc:
                raise last_exc
            raise RuntimeError("unreachable")
        return wrapper

    return decorator


def async_retry_with_backoff(
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[BaseException], ...] = (RetryableError,),
):
    """Async version of retry_with_backoff."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except NonRetryableError:
                    raise
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt == max_attempts:
                        log.error(f"[{func.__name__}] exhausted retries: {e}")
                        raise
                    delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                    if jitter:
                        delay = random.uniform(0, delay)
                    log.warning(
                        f"[{func.__name__}] attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
            if last_exc:
                raise last_exc
            raise RuntimeError("unreachable")
        return wrapper
    return decorator
