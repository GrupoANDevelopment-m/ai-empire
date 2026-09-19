"""
Self-Healing pattern for LangGraph nodes.

Implements the "Execute → Validate → Correct" loop:
  1. Run a tool/function
  2. Validate output against a schema/function
  3. If invalid: route back to a corrector that explains what to fix
  4. After N retries, escalate (HITL or different model)

Reference:
  https://langchain-ai.github.io/langgraph/
  https://tekko.id/en/blog/building-self-healing-ai-agents-with-langgraph-and-checkpoints
"""
from __future__ import annotations
import logging
import time
from enum import Enum
from typing import Callable, Any
from dataclasses import dataclass, field

log = logging.getLogger("empire.healing")


class HealingStrategy(str, Enum):
    RETRY = "retry"             # try the exact same thing again
    REPLAN = "replan"           # ask the LLM to re-think the plan
    MODEL_SWITCH = "model_switch"  # try a different model
    TOOL_SUBSTITUTE = "tool_substitute"  # use backup tool
    HUMAN_FALLBACK = "human_fallback"  # escalate to human
    GIVE_UP = "give_up"


@dataclass
class HealingResult:
    success: bool
    value: Any = None
    error: str | None = None
    attempts: int = 0
    strategy_used: HealingStrategy | None = None
    healing_history: list[dict] = field(default_factory=list)
    final_state: dict = field(default_factory=dict)


def validate_output(
    value: Any,
    schema: dict | None = None,
    required_keys: list[str] | None = None,
    predicate: Callable[[Any], tuple[bool, str]] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate a value against a schema, required keys, or a custom predicate.

    Returns (is_valid, error_message).
    """
    if value is None:
        return False, "value is None"

    if required_keys:
        if not isinstance(value, dict):
            return False, f"expected dict, got {type(value).__name__}"
        missing = [k for k in required_keys if k not in value]
        if missing:
            return False, f"missing required keys: {missing}"

    if schema:
        # Lightweight built-in validation (no external dep required)
        # Supports: type ("object", "integer", "string", "boolean", "number", "array"),
        # required, properties, minimum/maximum
        try:
            schema_type = schema.get("type")
            if schema_type:
                type_map = {
                    "object": dict, "array": list,
                    "string": str, "integer": int, "number": (int, float),
                    "boolean": bool, "null": type(None),
                }
                if schema_type in type_map:
                    if not isinstance(value, type_map[schema_type]):
                        return False, f"type mismatch: expected {schema_type}, got {type(value).__name__}"
            # Numeric bounds
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "minimum" in schema and value < schema["minimum"]:
                    return False, f"value {value} < minimum {schema['minimum']}"
                if "maximum" in schema and value > schema["maximum"]:
                    return False, f"value {value} > maximum {schema['maximum']}"
            # Required properties
            if schema.get("type") == "object" and "required" in schema:
                missing = [k for k in schema["required"] if k not in value]
                if missing:
                    return False, f"missing required properties: {missing}"
            # Property-level type checks
            if isinstance(value, dict) and "properties" in schema:
                for prop_name, prop_schema in schema["properties"].items():
                    if prop_name in value:
                        ptype = prop_schema.get("type")
                        if ptype and ptype in type_map:
                            if not isinstance(value[prop_name], type_map[ptype]):
                                return False, f"property '{prop_name}' has wrong type: expected {ptype}, got {type(value[prop_name]).__name__}"
        except Exception as e:
            return False, f"schema validation failed: {e}"

    if predicate:
        try:
            ok, msg = predicate(value)
            if not ok:
                return False, msg or "predicate returned False"
        except Exception as e:
            return False, f"predicate raised: {e}"

    return True, None


class SelfHealingNode:
    """
    Wraps a function with self-healing. On failure, runs through strategies
    in order until one succeeds or all are exhausted.

    Usage:
        heal = SelfHealingNode(
            name="extract_leads",
            func=my_extract_func,
            validate=lambda v: validate_output(v, required_keys=["name", "email"]),
            strategies=[HealingStrategy.RETRY, HealingStrategy.REPLAN, HealingStrategy.MODEL_SWITCH],
            max_attempts=3,
        )
        result = await heal.run(input_data)
    """

    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        validate: Callable[[Any], tuple[bool, str | None]] | None = None,
        strategies: list[HealingStrategy] = None,
        max_attempts: int = 3,
        backoff: float = 0.5,
        replan_fn: Callable | None = None,
        model_switch_fn: Callable | None = None,
    ):
        self.name = name
        self.func = func
        self.validate = validate
        self.strategies = strategies or [HealingStrategy.RETRY]
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.replan_fn = replan_fn
        self.model_switch_fn = model_switch_fn

    async def run(self, *args, **kwargs) -> HealingResult:
        history: list[dict] = []
        current_func = self.func
        last_error = "unknown"

        for attempt in range(1, self.max_attempts + 1):
            start = time.time()
            try:
                value = await _maybe_await(current_func(*args, **kwargs))
            except Exception as e:
                value = None
                last_error = f"{type(e).__name__}: {e}"
                log.warning(f"[{self.name}] attempt {attempt} raised: {last_error}")
                history.append({
                    "attempt": attempt, "strategy": "exception", "error": last_error,
                    "duration_ms": int((time.time() - start) * 1000),
                })
                # try next strategy
                if attempt < self.max_attempts:
                    current_func, last_strategy = self._next_strategy(
                        current_func, attempt, str(e)
                    )
                    if last_strategy == HealingStrategy.GIVE_UP:
                        break
                    time.sleep(self.backoff * attempt)
                continue

            # Ran without exception — validate
            is_valid, validation_error = (
                self.validate(value) if self.validate else (True, None)
            )
            duration_ms = int((time.time() - start) * 1000)

            if is_valid:
                history.append({
                    "attempt": attempt, "strategy": "ok",
                    "duration_ms": duration_ms,
                })
                return HealingResult(
                    success=True,
                    value=value,
                    attempts=attempt,
                    healing_history=history,
                )

            last_error = validation_error or "validation failed"
            log.warning(f"[{self.name}] attempt {attempt} invalid: {last_error}")
            history.append({
                "attempt": attempt, "strategy": "validation_failed",
                "error": last_error, "duration_ms": duration_ms,
            })
            if attempt < self.max_attempts:
                current_func, last_strategy = self._next_strategy(
                    current_func, attempt, last_error
                )
                if last_strategy == HealingStrategy.GIVE_UP:
                    break
                time.sleep(self.backoff * attempt)

        return HealingResult(
            success=False,
            error=last_error,
            attempts=self.max_attempts,
            strategy_used=last_strategy if history else None,
            healing_history=history,
        )

    def _next_strategy(self, current_func, attempt, error) -> tuple[Callable, HealingStrategy]:
        """Pick the next strategy to try."""
        # Cycle through strategies by attempt number
        strategy_idx = min(attempt, len(self.strategies) - 1)
        strategy = self.strategies[strategy_idx]
        log.info(f"[{self.name}] applying strategy: {strategy.value}")

        if strategy == HealingStrategy.RETRY:
            return current_func, strategy
        if strategy == HealingStrategy.REPLAN and self.replan_fn:
            new_func = self.replan_fn(current_func, error)
            return new_func or current_func, strategy
        if strategy == HealingStrategy.MODEL_SWITCH and self.model_switch_fn:
            new_func = self.model_switch_fn(current_func)
            return new_func or current_func, strategy
        if strategy == HealingStrategy.TOOL_SUBSTITUTE:
            # Caller provides via replan_fn typically
            return current_func, strategy
        if strategy == HealingStrategy.HUMAN_FALLBACK:
            log.error(f"[{self.name}] escalating to human: {error}")
            return current_func, strategy
        if strategy == HealingStrategy.GIVE_UP:
            return current_func, strategy
        return current_func, strategy


# ---- LangGraph-compatible nodes ----
async def validator_node(state: dict) -> dict:
    """LangGraph node: validates the last output. Adds `validation_error` to state if invalid."""
    last_output = state.get("last_output")
    schema = state.get("validation_schema")
    required = state.get("validation_required_keys")

    is_valid, err = validate_output(last_output, schema=schema, required_keys=required)
    state["is_valid"] = is_valid
    state["validation_error"] = err
    state["attempt_count"] = state.get("attempt_count", 0) + 1
    return state


async def corrector_node(state: dict) -> dict:
    """LangGraph node: uses an LLM to rewrite the last input/output, given the error."""
    # Lazy import to avoid hard dependency on LLM stack during validation tests
    try:
        from resilience.gateway_client import AIGateway, ChatMessage
    except Exception:
        AIGateway = None

    error = state.get("validation_error", "unknown")
    last_output = state.get("last_output")
    last_input = state.get("last_input", {})

    if state.get("attempt_count", 0) > 3:
        state["awaiting_human"] = True
        return state

    gw = AIGateway()
    prompt = f"""The previous attempt produced invalid output. Error: {error}

Previous output: {last_output}
Input was: {last_input}

Explain in 2-3 sentences what went wrong and how to fix it on the next attempt.
Then produce a corrected version of the input parameters that would likely succeed.
Output JSON with keys: "diagnosis" (string), "corrected_input" (object).
"""
    resp = await gw.chat(
        [ChatMessage(role="user", content=prompt)],
        model="auto",
        max_tokens=1024,
    )

    import json
    try:
        # Try to extract JSON from response
        text = resp.content
        if "{" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
        else:
            data = {"diagnosis": text, "corrected_input": last_input}
    except Exception:
        data = {"diagnosis": resp.content, "corrected_input": last_input}

    state["correction"] = data
    state["last_input"] = data.get("corrected_input", last_input)
    return state


async def _maybe_await(value):
    if hasattr(value, "__await__"):
        return await value
    return value
