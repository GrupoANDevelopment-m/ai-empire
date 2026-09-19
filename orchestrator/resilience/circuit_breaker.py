"""
Circuit Breaker — protect upstream providers from cascading failures.

States:
  - CLOSED: requests pass through, failures are counted
  - OPEN: requests fail fast (CircuitOpenError), no upstream call
  - HALF_OPEN: a single probe request is allowed through to test recovery

The breaker tracks a rolling window of failures. When the failure count
crosses `failure_threshold` within `failure_window_seconds`, the circuit
opens. After `recovery_timeout_seconds` it transitions to half-open, lets
one probe through, and either closes (success) or reopens (failure).

Thread-safe. Async-safe. No external dependencies.
"""
from __future__ import annotations
import time
import threading
import asyncio
from enum import Enum
from collections import deque
from typing import Callable, TypeVar, Any


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open. Includes retry_after hint."""
    def __init__(self, name: str, retry_after: float, last_error: str | None = None):
        self.name = name
        self.retry_after = retry_after
        self.last_error = last_error
        super().__init__(f"Circuit '{name}' is OPEN. Retry after {retry_after:.1f}s. Last error: {last_error}")


T = TypeVar("T")


class CircuitBreaker:
    """
    Per-provider circuit breaker.

    Usage:
        breaker = CircuitBreaker("anthropic", failure_threshold=5, recovery_timeout=30)
        try:
            result = breaker.call(lambda: client.messages.create(...))
        except CircuitOpenError:
            # fall back to another provider
            ...
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        failure_window: float = 60.0,
        success_threshold: int = 1,
        expected_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_window = failure_window
        self.success_threshold = success_threshold
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failures: deque[float] = deque()  # timestamps of recent failures
        self._consecutive_successes = 0
        self._opened_at: float | None = None
        self._last_error: str | None = None
        self._lock = threading.RLock()

    # ---- State queries ----
    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_from_open()
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def failure_count(self) -> int:
        with self._lock:
            self._prune_old_failures()
            return len(self._failures)

    def stats(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "failures_in_window": len(self._failures),
                "consecutive_successes": self._consecutive_successes,
                "opened_at": self._opened_at,
                "last_error": self._last_error,
            }

    # ---- Call wrappers ----
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Synchronous call through the circuit breaker."""
        with self._lock:
            self._maybe_transition_from_open()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    self.name,
                    self._seconds_until_recovery(),
                    self._last_error,
                )
            # Track whether we're in HALF_OPEN so a successful probe can close it
            was_half_open = self._state == CircuitState.HALF_OPEN

        try:
            result = func(*args, **kwargs)
        except self.expected_exceptions as e:
            with self._lock:
                self._record_failure(str(e))
            raise
        except BaseException:
            with self._lock:
                if was_half_open:
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
            raise

        with self._lock:
            # If we were probing and succeeded, force state back to HALF_OPEN
            # so _record_success can transition to CLOSED properly.
            if was_half_open:
                self._state = CircuitState.HALF_OPEN
            self._record_success()
        return result

    async def async_call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Async call through the circuit breaker."""
        with self._lock:
            self._maybe_transition_from_open()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    self.name,
                    self._seconds_until_recovery(),
                    self._last_error,
                )
            was_half_open = self._state == CircuitState.HALF_OPEN

        try:
            result = await func(*args, **kwargs)
        except self.expected_exceptions as e:
            with self._lock:
                self._record_failure(str(e))
            raise
        except BaseException:
            with self._lock:
                if was_half_open:
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
            raise

        with self._lock:
            if was_half_open:
                self._state = CircuitState.HALF_OPEN
            self._record_success()
        return result

    def reset(self) -> None:
        """Manually reset to CLOSED. Useful for ops / tests."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures.clear()
            self._consecutive_successes = 0
            self._opened_at = None
            self._last_error = None

    # ---- Internal ----
    def _maybe_transition_from_open(self) -> None:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._consecutive_successes = 0

    def _seconds_until_recovery(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = time.time() - self._opened_at
        return max(0.0, self.recovery_timeout - elapsed)

    def _prune_old_failures(self) -> None:
        cutoff = time.time() - self.failure_window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _record_failure(self, error: str) -> None:
        self._prune_old_failures()
        self._failures.append(time.time())
        self._last_error = error
        if self._state == CircuitState.HALF_OPEN:
            # Probe failed → reopen
            self._state = CircuitState.OPEN
            self._opened_at = time.time()
        elif len(self._failures) >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.time()

    def _record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failures.clear()
                self._consecutive_successes = 0
                self._opened_at = None
        else:
            self._consecutive_successes += 1
