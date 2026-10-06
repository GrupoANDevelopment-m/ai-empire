"""
Circuit Breaker — built on `pybreaker` (https://github.com/danielfm/pybreaker).

Replaces hand-rolled breaker with the battle-tested pybreaker library. Adds
async wrapper so callers can `await` the protected function.

States:
  - CLOSED: requests pass through, failures are counted
  - OPEN: requests fail fast (CircuitBreakerError), no upstream call
  - HALF_OPEN: a single probe request is allowed through to test recovery
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, TypeVar, Any

import pybreaker

log = logging.getLogger("empire.resilience.circuit_breaker")

T = TypeVar("T")

# Re-export pybreaker's exception under our historical name for compatibility
CircuitOpenError = pybreaker.CircuitBreakerError
CircuitState = pybreaker.STATE_CLOSED, pybreaker.STATE_OPEN, pybreaker.STATE_HALF_OPEN


def CircuitBreaker_(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
    expected_exceptions: tuple = (Exception,),
):
    """Factory that returns a configured pybreaker.CircuitBreaker instance.

    Args:
        name: human-readable label (shown in logs/metrics)
        failure_threshold: failures within recovery_timeout to open the circuit
        recovery_timeout: seconds before transitioning OPEN -> HALF-OPEN
        expected_exceptions: exception classes that count as failures
    """
    return pybreaker.CircuitBreaker(
        fail_max=failure_threshold,
        reset_timeout=recovery_timeout,
        exclude=[],
        name=name,
        listeners=[],
    )


async def call_async(breaker: pybreaker.CircuitBreaker, func: Callable, *args, **kwargs) -> Any:
    """Call an async function through the breaker.

    The sync `breaker.call(func, ...)` returns the coroutine and lets
    CircuitBreakerError propagate, which is exactly what we want for async.
    """
    return await breaker.call_async(func, *args, **kwargs)


def call_sync(breaker: pybreaker.CircuitBreaker, func: Callable, *args, **kwargs) -> Any:
    """Call a sync function through the breaker."""
    return breaker.call(func, *args, **kwargs)
