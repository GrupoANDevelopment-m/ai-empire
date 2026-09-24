"""
Rate limiting — Redis-backed token bucket.

Per (tenant, api_key) and per (tenant, "agent"). Configurable via env:
  RATE_LIMIT_PER_MIN=60   — global per API key
  RATE_LIMIT_BURST=120    — burst capacity
  RATE_LIMIT_AGENT=20     — agent (LLM) calls per tenant per minute

Returns 429 Too Many Requests with Retry-After header when exceeded.
Falls back to in-memory limiter if Redis is unavailable (development).
"""
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int, key: str, limit: int):
        self.retry_after = retry_after
        self.key = key
        self.limit = limit
        super().__init__(f"rate limit exceeded for {key} (limit {limit}/min)")


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimiter:
    """
    Token-bucket rate limiter.

    Backends:
      - Redis (production): shared across instances, atomic via Lua script
      - In-memory (fallback): per-process, lost on restart

    The Lua script atomically checks and decrements — avoids race conditions
    across multiple agent instances.
    """
    _LUA = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_per_sec = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local cost = tonumber(ARGV[4])

    local data = redis.call('HMGET', key, 'tokens', 'ts')
    local tokens = tonumber(data[1]) or capacity
    local ts    = tonumber(data[2]) or now

    local delta  = math.max(0, now - ts)
    tokens = math.min(capacity, tokens + delta * refill_per_sec)
    local allowed = 0
    if tokens >= cost then
      tokens = tokens - cost
      allowed = 1
    end
    redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
    redis.call('EXPIRE', key, 3600)
    return {allowed, tokens}
    """

    def __init__(self, redis_url: Optional[str] = None,
                 default_per_min: int = 60,
                 default_burst: int = 120):
        self.per_min = int(os.getenv("RATE_LIMIT_PER_MIN", default_per_min))
        self.burst = int(os.getenv("RATE_LIMIT_BURST", default_burst))
        self._redis = None
        self._mem_buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=self.burst, last_refill=time.time())
        )
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url)
                self._redis.ping()
            except Exception:
                self._redis = None  # fall back to in-memory

    def check(self, key: str, cost: float = 1.0) -> tuple[bool, float]:
        """
        Try to spend `cost` tokens for `key`. Returns (allowed, remaining).
        """
        capacity = self.burst
        refill_per_sec = self.per_min / 60.0
        now = time.time()

        if self._redis:
            try:
                result = self._redis.eval(
                    self._LUA, 1, f"ratelimit:{key}",
                    capacity, refill_per_sec, now, cost,
                )
                allowed, remaining = result[0], result[1]
                return bool(allowed), float(remaining)
            except Exception:
                # Redis hiccup — fall through to in-memory
                pass

        # In-memory fallback
        b = self._mem_buckets[key]
        delta = max(0, now - b.last_refill)
        b.tokens = min(capacity, b.tokens + delta * refill_per_sec)
        b.last_refill = now
        if b.tokens >= cost:
            b.tokens -= cost
            return True, b.tokens
        return False, b.tokens

    def enforce(self, key: str, cost: float = 1.0) -> None:
        """Raise RateLimitExceeded if not allowed."""
        allowed, remaining = self.check(key, cost)
        if not allowed:
            retry = int((cost - remaining) / (self.per_min / 60.0)) + 1
            raise RateLimitExceeded(retry_after=retry, key=key,
                                    limit=int(self.per_min))


# Singleton — created at app startup, configured from env
_default_limiter: Optional[RateLimiter] = None


def get_limiter() -> RateLimiter:
    global _default_limiter
    if _default_limiter is None:
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        _default_limiter = RateLimiter(redis_url=redis_url)
    return _default_limiter
