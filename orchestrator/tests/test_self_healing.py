"""
REAL tests for self-healing.

Verify:
  - Successful run on first try
  - Validation failure triggers retry
  - Strategy escalation: retry → replan → model switch
  - Max attempts respected
  - Healing history recorded
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from healing.self_healing import (
    SelfHealingNode, HealingStrategy, HealingResult,
    validate_output, validator_node, corrector_node,
)


# ============================================================================
# validate_output
# ============================================================================

class TestValidateOutput:

    def test_none_is_invalid(self):
        ok, err = validate_output(None)
        assert not ok
        assert "None" in err

    def test_required_keys_missing(self):
        ok, err = validate_output({"name": "x"}, required_keys=["name", "email"])
        assert not ok
        assert "email" in err

    def test_required_keys_present(self):
        ok, err = validate_output({"name": "x", "email": "y"}, required_keys=["name", "email"])
        assert ok
        assert err is None

    def test_required_keys_value_not_dict(self):
        ok, err = validate_output("not a dict", required_keys=["x"])
        assert not ok
        assert "dict" in err

    def test_schema_validation(self):
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 0}},
            "required": ["age"],
        }
        # Valid
        ok, _ = validate_output({"age": 25}, schema=schema)
        assert ok
        # Invalid (wrong type)
        ok, err = validate_output({"age": "twenty-five"}, schema=schema)
        assert not ok
        assert err is not None
        # Invalid (missing)
        ok, err = validate_output({}, schema=schema)
        assert not ok

    def test_custom_predicate(self):
        def must_be_positive(v):
            if not isinstance(v, (int, float)) or v <= 0:
                return False, "must be positive"
            return True, None

        ok, _ = validate_output(5, predicate=must_be_positive)
        assert ok
        ok, err = validate_output(-1, predicate=must_be_positive)
        assert not ok
        assert "positive" in err


# ============================================================================
# SelfHealingNode
# ============================================================================

class TestSelfHealingNode:

    @pytest.mark.asyncio
    async def test_succeeds_first_try(self):
        """No healing needed when first call succeeds."""
        calls = []
        def good(x):
            calls.append(x)
            return {"result": x * 2}

        heal = SelfHealingNode(
            name="test",
            func=good,
            validate=lambda v: validate_output(v, required_keys=["result"]),
        )
        result = await heal.run(5)
        assert result.success
        assert result.value == {"result": 10}
        assert result.attempts == 1
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retries_on_validation_failure(self):
        """When validation fails, retry with same strategy."""
        attempts = []
        def sometimes_bad(x):
            attempts.append(x)
            if len(attempts) < 3:
                return {"incomplete": True}  # missing "result"
            return {"result": "ok"}

        heal = SelfHealingNode(
            name="test",
            func=sometimes_bad,
            validate=lambda v: validate_output(v, required_keys=["result"]),
            max_attempts=5,
            backoff=0.001,
        )
        result = await heal.run(1)
        assert result.success
        assert result.attempts == 3
        assert len(attempts) == 3
        # History records both failures and the final success
        assert any(h["strategy"] == "validation_failed" for h in result.healing_history)
        assert any(h["strategy"] == "ok" for h in result.healing_history)

    @pytest.mark.asyncio
    async def test_retries_on_exception(self):
        """Exception in func triggers retry."""
        attempts = []
        def sometimes_raises():
            attempts.append(1)
            if len(attempts) < 2:
                raise ValueError("flaky")
            return {"ok": True}

        heal = SelfHealingNode(
            name="test",
            func=sometimes_raises,
            validate=lambda v: validate_output(v, required_keys=["ok"]),
            max_attempts=3,
            backoff=0.001,
        )
        result = await heal.run()
        assert result.success
        assert result.attempts == 2

    @pytest.mark.asyncio
    async def test_exhausts_attempts_on_persistent_failure(self):
        """All attempts fail, return failure result."""
        def always_bad():
            return {"incomplete": True}

        heal = SelfHealingNode(
            name="test",
            func=always_bad,
            validate=lambda v: validate_output(v, required_keys=["result"]),
            max_attempts=3,
            backoff=0.001,
        )
        result = await heal.run()
        assert not result.success
        assert result.attempts == 3
        assert "missing required keys" in result.error

    @pytest.mark.asyncio
    async def test_replan_strategy_changes_func(self):
        """When replan strategy is invoked, a new function is used."""
        calls = []
        def bad(x):
            calls.append(("bad", x))
            return {"incomplete": True}

        def good(x):
            calls.append(("good", x))
            return {"result": "ok"}

        def replanner(current_func, error):
            return good

        heal = SelfHealingNode(
            name="test",
            func=bad,
            validate=lambda v: validate_output(v, required_keys=["result"]),
            strategies=[HealingStrategy.RETRY, HealingStrategy.REPLAN],
            max_attempts=2,
            backoff=0.001,
            replan_fn=replanner,
        )
        result = await heal.run(42)
        assert result.success
        assert ("bad", 42) in calls
        assert ("good", 42) in calls

    @pytest.mark.asyncio
    async def test_model_switch_strategy(self):
        def bad(x):
            return {"incomplete": True}
        def smart(x):
            return {"result": "smart"}

        heal = SelfHealingNode(
            name="test",
            func=bad,
            validate=lambda v: validate_output(v, required_keys=["result"]),
            strategies=[HealingStrategy.RETRY, HealingStrategy.MODEL_SWITCH],
            max_attempts=2,
            backoff=0.001,
            model_switch_fn=lambda f: smart,
        )
        result = await heal.run(1)
        assert result.success

    @pytest.mark.asyncio
    async def test_async_function_supported(self):
        async def good(x):
            return {"result": x}

        heal = SelfHealingNode(
            name="async-test",
            func=good,
            validate=lambda v: validate_output(v, required_keys=["result"]),
        )
        result = await heal.run("hello")
        assert result.success
        assert result.value == {"result": "hello"}

    @pytest.mark.asyncio
    async def test_human_fallback_strategy(self):
        """When all else fails, human_fallback strategy escalates."""
        heal = SelfHealingNode(
            name="test",
            func=lambda: {"incomplete": True},
            validate=lambda v: validate_output(v, required_keys=["result"]),
            strategies=[HealingStrategy.RETRY, HealingStrategy.HUMAN_FALLBACK],
            max_attempts=2,
            backoff=0.001,
        )
        result = await heal.run()
        assert not result.success
        assert result.strategy_used == HealingStrategy.HUMAN_FALLBACK

    @pytest.mark.asyncio
    async def test_healing_history_records_attempts(self):
        def always_bad():
            return {"wrong": "shape"}
        heal = SelfHealingNode(
            name="test",
            func=always_bad,
            validate=lambda v: validate_output(v, required_keys=["result"]),
            max_attempts=3,
            backoff=0.001,
        )
        result = await heal.run()
        assert len(result.healing_history) == 3
        assert all(h["strategy"] == "validation_failed" for h in result.healing_history)
        assert all(h["duration_ms"] >= 0 for h in result.healing_history)


# ============================================================================
# LangGraph nodes
# ============================================================================

class TestLangGraphNodes:

    @pytest.mark.asyncio
    async def test_validator_node_marks_valid(self):
        state = {
            "last_output": {"name": "test", "email": "x@y.com"},
            "validation_required_keys": ["name", "email"],
        }
        result = await validator_node(state)
        assert result["is_valid"]
        assert result["validation_error"] is None
        assert result["attempt_count"] == 1

    @pytest.mark.asyncio
    async def test_validator_node_marks_invalid(self):
        state = {
            "last_output": {"name": "test"},
            "validation_required_keys": ["name", "email"],
        }
        result = await validator_node(state)
        assert not result["is_valid"]
        assert "email" in result["validation_error"]

    @pytest.mark.asyncio
    async def test_corrector_node_escalates_after_max_attempts(self):
        """After 3 attempts, corrector_node sets awaiting_human=True."""
        state = {
            "last_output": {"bad": "shape"},
            "last_input": {"x": 1},
            "validation_error": "missing key",
            "attempt_count": 4,
        }
        # No actual LLM call needed because we short-circuit
        result = await corrector_node(state)
        assert result["awaiting_human"] is True
