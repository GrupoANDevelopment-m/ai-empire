"""Test circuit breaker (pybreaker-backed)."""
import pytest
from orchestrator.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError


class TestCircuitBreaker:
    
    def test_starts_closed(self):
        cb = CircuitBreaker(name="test", fail_max=3)
        assert cb.state == "closed"
    
    def test_opens_after_failures(self):
        cb = CircuitBreaker(name="test", fail_max=3, reset_timeout=1)
        for _ in range(3):
            try:
                with cb:
                    raise ValueError("fail")
            except ValueError:
                pass
        assert cb.state == "open"
    
    def test_rejects_when_open(self):
        cb = CircuitBreaker(name="test", fail_max=2, reset_timeout=10)
        for _ in range(2):
            try:
                with cb:
                    raise ValueError("fail")
            except ValueError:
                pass
        with pytest.raises(CircuitOpenError):
            with cb:
                pass
    
    def test_successful_calls_keep_closed(self):
        cb = CircuitBreaker(name="test", fail_max=3)
        for _ in range(10):
            with cb:
                pass
        assert cb.state == "closed"
