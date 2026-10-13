"""Test retry (tenacity-backed)."""
import pytest
from orchestrator.resilience.retry import retry_with_backoff, RetryExhausted


class TestRetry:
    
    def test_succeeds_first_try(self):
        calls = []
        @retry_with_backoff(max_attempts=3)
        def func():
            calls.append(1)
            return "ok"
        assert func() == "ok"
        assert len(calls) == 1
    
    def test_retries_on_failure(self):
        calls = []
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def func():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("transient")
            return "ok"
        assert func() == "ok"
        assert len(calls) == 3
    
    def test_exhausts_retries(self):
        calls = []
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def func():
            calls.append(1)
            raise ValueError("always fails")
        with pytest.raises(RetryExhausted):
            func()
        assert len(calls) == 3
