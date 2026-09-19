"""
End-to-end tests of the self-healing pipeline.

These run an actual LangGraph-style state machine with real nodes,
real validation, and a mock LLM (we can't always rely on a real LLM
in CI, so the mock simulates tool failures and LLM corrections).
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from healing.self_healing import (
    SelfHealingNode, HealingStrategy, HealingResult,
    validate_output, validator_node, corrector_node,
)


class TestE2ESelfHealing:
    """Full pipeline: run → fail → validate → correct → retry → succeed."""

    @pytest.mark.asyncio
    async def test_full_healing_loop_with_mock_llm(self):
        """
        Simulate a tool that produces bad output 2 times, then good output.
        The validator catches it, the corrector "fixes" the input.
        """
        attempt_count = [0]
        corrected_inputs = []

        def tool(input_data):
            attempt_count[0] += 1
            corrected_inputs.append(input_data.copy())
            # First 2 attempts: missing required key
            if attempt_count[0] < 3:
                return {"incomplete": True, "attempt": attempt_count[0]}
            # 3rd attempt: success
            return {
                "name": input_data.get("name", ""),
                "result": "success",
            }

        heal = SelfHealingNode(
            name="extract",
            func=tool,
            validate=lambda v: validate_output(v, required_keys=["name", "result"]),
            strategies=[HealingStrategy.RETRY, HealingStrategy.REPLAN],
            max_attempts=4,
            backoff=0.001,
            replan_fn=lambda current, err: tool,  # same tool, but caller could swap
        )
        result = await heal.run({"name": "Acme"})
        assert result.success
        assert result.attempts == 3
        assert result.value["result"] == "success"
        assert len(result.healing_history) == 3

    @pytest.mark.asyncio
    async def test_healing_eventually_gives_up(self):
        """When all strategies fail, return failure result, don't hang."""
        def always_fails(input_data):
            return {"wrong": "shape"}

        heal = SelfHealingNode(
            name="never-works",
            func=always_fails,
            validate=lambda v: validate_output(v, required_keys=["expected"]),
            strategies=[HealingStrategy.RETRY, HealingStrategy.REPLAN, HealingStrategy.MODEL_SWITCH],
            max_attempts=3,
            backoff=0.001,
        )
        result = await heal.run({})
        assert not result.success
        assert result.attempts == 3
        assert "missing required keys" in result.error

    @pytest.mark.asyncio
    async def test_concurrent_healing_runs(self):
        """10 self-healing nodes run in parallel without interference."""
        async def make_good(x):
            return {"result": x, "value": x * 2}

        heal = SelfHealingNode(
            name="good",
            func=make_good,
            validate=lambda v: validate_output(v, required_keys=["result", "value"]),
        )
        results = await asyncio.gather(*[heal.run(i) for i in range(20)])
        assert all(r.success for r in results)
        assert [r.value["value"] for r in results] == [i * 2 for i in range(20)]

    @pytest.mark.asyncio
    async def test_validator_corrector_graph_node_interaction(self):
        """
        The validator_node + corrector_node work together as a LangGraph subgraph.
        """
        # State after first failed run
        state = {
            "last_output": {"incomplete": True},
            "last_input": {"query": "test"},
            "validation_required_keys": ["answer"],
            "validation_error": "missing key: answer",
            "attempt_count": 1,
        }

        # Validator
        state = await validator_node(state)
        assert not state["is_valid"]
        assert "answer" in state["validation_error"]

        # Corrector (uses a real gateway, but with mock LLM if no key)
        # Here we just verify it short-circuits after max attempts
        state["attempt_count"] = 4  # already over limit
        state = await corrector_node(state)
        assert state.get("awaiting_human") is True


class TestE2EResilienceStack:
    """Circuit breaker + retry + fallback stacked together."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_retry_storm(self):
        """When service is down, circuit opens, retries stop early."""
        from resilience.circuit_breaker import CircuitBreaker, CircuitOpenError
        from resilience.retry import retry_with_backoff, RetryableError

        cb = CircuitBreaker("svc", failure_threshold=2, recovery_timeout=10)
        call_count = [0]

        @retry_with_backoff(max_attempts=10, base_delay=0.001, max_delay=0.01)
        def call():
            call_count[0] += 1
            cb.call(lambda: (_ for _ in ()).throw(ConnectionError("down")))
            return "ok"

        # The retry decorator calls the function 10 times.
        # Each call goes through the breaker, which fails 2 times then opens.
        with pytest.raises((ConnectionError, CircuitOpenError)):
            try:
                call()
            except CircuitOpenError:
                raise
        # Should have stopped early (way less than 10 attempts)
        assert call_count[0] < 10

    @pytest.mark.asyncio
    async def test_fallback_chain_with_circuit_breaker(self):
        """Fallback to next backend when circuit is open on the first."""
        from resilience.circuit_breaker import CircuitBreaker
        from resilience.fallback import AsyncFallbackChain, FallbackStep

        # Backend A has open circuit
        cb_a = CircuitBreaker("a", failure_threshold=1, recovery_timeout=60)
        for _ in range(2):
            try:
                cb_a.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
            except Exception:
                pass
        assert cb_a.is_open

        async def call_a():
            cb_a.call(lambda: "should not reach")
            return "a"

        async def call_b():
            return "b"

        chain = AsyncFallbackChain([
            FallbackStep("a", call_a),
            FallbackStep("b", call_b),
        ])
        result = await chain.run()
        assert result == "b"
        assert len(chain.attempts) == 2
