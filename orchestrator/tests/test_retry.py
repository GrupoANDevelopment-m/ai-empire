"""
REAL tests for retry_with_backoff.

Verify:
  - Retries on RetryableError
  - Does NOT retry on NonRetryableError
  - Exponential backoff with jitter
  - Max attempts honored
  - Last error is raised after exhaustion
"""
import time
import pytest
from unittest.mock import patch

from resilience.retry import (
    retry_with_backoff, async_retry_with_backoff,
    RetryableError, NonRetryableError, classify_http_error,
)


class TestSyncRetry:

    def test_success_no_retry(self):
        """Successful call doesn't trigger any retry."""
        calls = []

        @retry_with_backoff(max_attempts=3)
        def good():
            calls.append(1)
            return "ok"

        assert good() == "ok"
        assert len(calls) == 1

    def test_retries_on_retryable_error(self):
        """RetryableError triggers retries up to max_attempts."""
        attempts = []

        @retry_with_backoff(max_attempts=3, base_delay=0.001, max_delay=0.01)
        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise RetryableError(f"attempt {len(attempts)}")
            return "success"

        assert flaky() == "success"
        assert len(attempts) == 3

    def test_does_not_retry_non_retryable(self):
        """NonRetryableError fails immediately."""
        attempts = []

        @retry_with_backoff(max_attempts=5, base_delay=0.001)
        def fail():
            attempts.append(1)
            raise NonRetryableError("fatal")

        with pytest.raises(NonRetryableError):
            fail()
        assert len(attempts) == 1  # no retry

    def test_exhausts_max_attempts(self):
        """After max_attempts, the last error is raised."""
        attempts = []

        @retry_with_backoff(max_attempts=4, base_delay=0.001, max_delay=0.01)
        def always_fail():
            attempts.append(1)
            raise RetryableError("persistent")

        with pytest.raises(RetryableError, match="persistent"):
            always_fail()
        assert len(attempts) == 4

    def test_exponential_backoff_timing(self):
        """Verify backoff actually delays (not zero)."""
        times = []

        @retry_with_backoff(max_attempts=3, base_delay=0.05, backoff_factor=2, jitter=False)
        def fails_fast():
            times.append(time.time())
            if len(times) < 3:
                raise RetryableError("again")
            return "done"

        result = fails_fast()
        assert result == "done"
        assert len(times) == 3
        # Delay 1 ≈ 0.05, delay 2 ≈ 0.1
        gap1 = times[1] - times[0]
        gap2 = times[2] - times[1]
        assert gap1 >= 0.04  # tolerance
        assert gap2 >= 0.08
        # Second delay should be larger
        assert gap2 > gap1

    def test_max_delay_caps_backoff(self):
        """Backoff never exceeds max_delay."""
        @retry_with_backoff(max_attempts=5, base_delay=1.0, max_delay=0.05, backoff_factor=10, jitter=False)
        def fails():
            raise RetryableError("x")

        start = time.time()
        with pytest.raises(RetryableError):
            fails()
        elapsed = time.time() - start
        # 4 sleeps, each capped at 0.05s = max 0.2s total
        assert elapsed < 1.0  # should be much less than uncapped

    def test_jitter_adds_randomness(self):
        """Jitter causes varying delays (not exact exponential)."""
        with patch("resilience.retry.random.uniform", return_value=0.025):
            # With jitter, even if backoff would be 0.05, the actual sleep is 0.025
            times = []

            @retry_with_backoff(max_attempts=2, base_delay=0.1, max_delay=1.0, jitter=True)
            def fail():
                times.append(time.time())
                raise RetryableError("x")

            with pytest.raises(RetryableError):
                fail()

            # 1 sleep, should be 0.025 (mocked)
            assert times[1] - times[0] < 0.1  # less than uncapped


class TestAsyncRetry:

    @pytest.mark.asyncio
    async def test_async_success(self):
        @async_retry_with_backoff(max_attempts=3)
        async def good():
            return "ok"

        assert await good() == "ok"

    @pytest.mark.asyncio
    async def test_async_retries(self):
        attempts = []

        @async_retry_with_backoff(max_attempts=3, base_delay=0.001)
        async def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise RetryableError("again")
            return "ok"

        assert await flaky() == "ok"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_async_does_not_retry_non_retryable(self):
        attempts = []

        @async_retry_with_backoff(max_attempts=5, base_delay=0.001)
        async def fatal():
            attempts.append(1)
            raise NonRetryableError("nope")

        with pytest.raises(NonRetryableError):
            await fatal()
        assert len(attempts) == 1


class TestErrorClassification:

    def test_classify_retryable_codes(self):
        for code in [408, 425, 429, 500, 502, 503, 504, 529]:
            assert classify_http_error(code) is RetryableError, f"code {code} should be retryable"

    def test_classify_non_retryable_codes(self):
        for code in [400, 401, 403, 404, 422]:
            assert classify_http_error(code) is NonRetryableError, f"code {code} should not be retryable"
