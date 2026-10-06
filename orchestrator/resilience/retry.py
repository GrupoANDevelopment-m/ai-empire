"""
Retry with exponential backoff + full jitter.

Built on `tenacity` (https://github.com/jd/tenacity) — battle-tested retry library.
We keep our HTTP-status classification helper on top.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, TypeVar
from functools import wraps

import tenacity

log = logging.getLogger("empire.resilience.retry")

T = TypeVar("T")


class RetryableError(Exception):
    """Marker for errors that should trigger a retry."""


class NonRetryableError(Exception):
    """Marker for errors that should NOT be retried (fail fast)."""


RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504, 529}
NON_RETRYABLE_HTTP_CODES = {400, 401, 403, 404, 422}


def classify_http_error(status: int, headers: dict | None = None) -> type[Exception]:
    if status in RETRYABLE_HTTP_CODES:
        return RetryableError
    if status in NON_RETRYABLE_HTTP_CODES:
        return NonRetryableError
    return RetryableError


def retry_with_backoff(
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[BaseException], ...] = (RetryableError,),
):
    """Decorator factory that returns a tenacity-based retry decorator.

    Drop-in replacement for the previous hand-rolled loop. Uses tenacity's
    ExponentialBackoff with optional RandomExponentialJitter.

    Example:
        @retry_with_backoff(max_attempts=3)
        async def call_api(...): ...
    """
    return tenacity.retry(
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential_jitter(
            initial=base_delay, max=max_delay, exp_base=backoff_factor,
        ) if jitter else tenacity.wait_exponential(
            multiplier=base_delay, max=max_delay, exp_base=backoff_factor,
        ),
        retry=tenacity.retry_if_exception_type(retryable_exceptions),
        reraise=True,
    )


# Pre-built tenacity decorator helpers — recommended entry point
retry_temporary = tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential_jitter(initial=1, max=10),
    retry=tenacity.retry_if_exception_type(RetryableError),
    reraise=True,
)


retry_aggressive = tenacity.retry(
    stop=tenacity.stop_after_attempt(8),
    wait=tenacity.wait_exponential_jitter(initial=2, max=60),
    retry=tenacity.retry_if_exception_type(RetryableError),
    reraise=True,
)
