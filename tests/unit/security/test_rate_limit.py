"""Test rate limiting."""
import time
import pytest
from empire.security.rate_limit import RateLimiter, RateLimitExceeded


class TestRateLimiter:
    """Test token-bucket rate limiter."""
    
    def test_allow_under_limit(self):
        """Should allow requests under the limit."""
        limiter = RateLimiter(rate=10, period=60)
        for _ in range(5):
            assert limiter.allow(key="test-key")
    
    def test_reject_over_limit(self):
        """Should reject requests over the limit."""
        limiter = RateLimiter(rate=3, period=60)
        for _ in range(3):
            assert limiter.allow(key="test-key")
        with pytest.raises(RateLimitExceeded):
            limiter.allow(key="test-key")
    
    def test_per_key_isolation(self):
        """Different keys should have separate buckets."""
        limiter = RateLimiter(rate=2, period=60)
        assert limiter.allow(key="key-a")
        assert limiter.allow(key="key-a")
        assert limiter.allow(key="key-b")  # different key
        assert limiter.allow(key="key-b")
    
    def test_refill(self):
        """Bucket should refill over time."""
        limiter = RateLimiter(rate=2, period=1)
        limiter.allow(key="k")
        limiter.allow(key="k")
        time.sleep(1.1)
        assert limiter.allow(key="k")
