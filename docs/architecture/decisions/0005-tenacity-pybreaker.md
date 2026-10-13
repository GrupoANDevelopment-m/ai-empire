# ADR-0005: Use Tenacity + PyBreaker for Resilience

## Status
Accepted — 2026-02-18

## Context
External services fail. We need:
1. **Retry** with exponential backoff
2. **Circuit breaker** to fail fast when service is down
3. **Fallback** to alternative providers

Options for retry: hand-rolled, tenacity, retry, backoff
Options for breaker: hand-rolled, pybreaker, circuitbreaker, aiobreaker

## Decision
- **tenacity** for retry (used by SQLAlchemy, Requests)
- **pybreaker** for circuit breaker (used by Yelp, Mozilla)

## Rationale
- Both are battle-tested in major OSS projects
- 2.5K+ LOC of hand-rolled code replaced with ~5K LOC of mature libraries
- Active maintenance and CVE patches
- Better error messages and observability

## Configuration
```python
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    before_sleep=before_sleep_log(log, logging.WARNING),
)
async def call_llm():
    ...

# Circuit breaker
class LLMBreaker(CircuitBreaker):
    fail_max = 5
    reset_timeout = 60
```
