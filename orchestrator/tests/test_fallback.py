"""
REAL tests for FallbackChain.

Verify:
  - Returns first successful result
  - Skips failing steps
  - Returns default if all fail
  - Raises FallbackExhausted if no default and all fail
  - Records attempt history
"""
import pytest

from resilience.fallback import FallbackChain, AsyncFallbackChain, FallbackStep, FallbackExhausted


class TestSyncFallback:

    def test_returns_first_success(self):
        chain = FallbackChain([
            FallbackStep("a", lambda: 1),
            FallbackStep("b", lambda: 2),
        ])
        assert chain.run() == 1
        assert len(chain.attempts) == 1
        assert chain.attempts[0]["name"] == "a"
        assert chain.attempts[0]["status"] == "ok"

    def test_skips_failing_steps(self):
        def fail():
            raise ValueError("nope")
        chain = FallbackChain([
            FallbackStep("a", fail),
            FallbackStep("b", fail),
            FallbackStep("c", lambda: "got it"),
        ])
        assert chain.run() == "got it"
        assert len(chain.attempts) == 3
        assert chain.attempts[0]["status"] == "error"
        assert chain.attempts[1]["status"] == "error"
        assert chain.attempts[2]["status"] == "ok"

    def test_all_fail_returns_default(self):
        chain = FallbackChain(
            [FallbackStep("a", lambda: (_ for _ in ()).throw(RuntimeError("x"))),
             FallbackStep("b", lambda: (_ for _ in ()).throw(RuntimeError("y")))],
            default="graceful",
        )
        assert chain.run() == "graceful"
        assert all(a["status"] == "error" for a in chain.attempts)

    def test_all_fail_no_default_raises(self):
        chain = FallbackChain([
            FallbackStep("a", lambda: (_ for _ in ()).throw(RuntimeError("x"))),
        ])
        with pytest.raises(FallbackExhausted):
            chain.run()

    def test_empty_chain_returns_default(self):
        chain = FallbackChain([], default="nothing")
        assert chain.run() == "nothing"

    def test_empty_chain_no_default_raises(self):
        chain = FallbackChain([])
        with pytest.raises(FallbackExhausted):
            chain.run()

    def test_args_and_kwargs_passed(self):
        def add(a, b, multiplier=1):
            return (a + b) * multiplier

        chain = FallbackChain([
            FallbackStep("a", add, args=(1, 2), kwargs={"multiplier": 10}),
        ])
        assert chain.run() == 30

    def test_dynamic_add(self):
        chain = FallbackChain()
        chain.add(FallbackStep("a", lambda: "first"))
        assert chain.run() == "first"


class TestAsyncFallback:

    @pytest.mark.asyncio
    async def test_async_success(self):
        async def good():
            return "ok"
        chain = AsyncFallbackChain([FallbackStep("a", good)])
        assert await chain.run() == "ok"

    @pytest.mark.asyncio
    async def test_async_skips_failing(self):
        async def fail():
            raise ConnectionError("nope")
        async def good():
            return "finally"
        chain = AsyncFallbackChain([
            FallbackStep("a", fail),
            FallbackStep("b", good),
        ])
        assert await chain.run() == "finally"

    @pytest.mark.asyncio
    async def test_async_mixed_sync_and_async(self):
        """Fallback chain can mix sync and async functions."""
        async def async_fail():
            raise ValueError("async fail")
        def sync_ok():
            return "sync ok"
        chain = AsyncFallbackChain([
            FallbackStep("a", async_fail),
            FallbackStep("b", sync_ok),
        ])
        assert await chain.run() == "sync ok"

    @pytest.mark.asyncio
    async def test_async_all_fail_default(self):
        async def fail():
            raise RuntimeError("x")
        chain = AsyncFallbackChain(
            [FallbackStep("a", fail), FallbackStep("b", fail)],
            default="degraded",
        )
        assert await chain.run() == "degraded"
