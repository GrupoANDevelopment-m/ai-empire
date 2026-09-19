"""
Fallback chain — try multiple providers/models in order.
If all fail, return a default response (graceful degradation).
"""
from __future__ import annotations
import asyncio
import logging
from typing import Callable, TypeVar, Any
from dataclasses import dataclass

log = logging.getLogger("empire.resilience.fallback")

T = TypeVar("T")


class FallbackExhausted(Exception):
    """Raised when all fallbacks in the chain have been exhausted."""


@dataclass
class FallbackStep:
    name: str
    func: Callable[..., T]
    args: tuple = ()
    kwargs: dict = None

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


class FallbackChain:
    """
    Chain of fallbacks. Tries each in order; stops on first success.
    Logs each failure. On total failure, returns the `default` value
    (graceful degradation) OR raises FallbackExhausted.

    Usage:
        chain = FallbackChain([
            FallbackStep("anthropic", call_anthropic, kwargs={"prompt": p}),
            FallbackStep("openai",     call_openai,     kwargs={"prompt": p}),
            FallbackStep("ollama",     call_ollama,     kwargs={"prompt": p}),
        ], default="Service degraded, please retry.")
        result = chain.run()
    """

    def __init__(self, steps: list[FallbackStep] | None = None, default: Any = None):
        self.steps = steps or []
        self.default = default
        self.attempts: list[dict] = []

    def add(self, step: FallbackStep) -> "FallbackChain":
        self.steps.append(step)
        return self

    def run(self) -> Any:
        for step in self.steps:
            try:
                result = step.func(*step.args, **step.kwargs)
                self.attempts.append({
                    "name": step.name, "status": "ok", "duration_ms": 0,
                })
                return result
            except Exception as e:
                log.warning(f"[FallbackChain] step '{step.name}' failed: {e}")
                self.attempts.append({
                    "name": step.name, "status": "error", "error": str(e),
                })
                continue
        log.error(f"[FallbackChain] all {len(self.steps)} steps exhausted")
        if self.default is not None:
            return self.default
        raise FallbackExhausted(
            f"All {len(self.steps)} fallback steps exhausted. "
            f"Last errors: {self.attempts[-3:] if self.attempts else 'none'}"
        )


class AsyncFallbackChain:
    """Async version of FallbackChain."""

    def __init__(self, steps: list[FallbackStep] | None = None, default: Any = None):
        self.steps = steps or []
        self.default = default
        self.attempts: list[dict] = []

    def add(self, step: FallbackStep) -> "AsyncFallbackChain":
        self.steps.append(step)
        return self

    async def run(self) -> Any:
        for step in self.steps:
            try:
                if asyncio.iscoroutinefunction(step.func):
                    result = await step.func(*step.args, **step.kwargs)
                else:
                    result = step.func(*step.args, **step.kwargs)
                self.attempts.append({"name": step.name, "status": "ok"})
                return result
            except Exception as e:
                log.warning(f"[AsyncFallbackChain] step '{step.name}' failed: {e}")
                self.attempts.append({"name": step.name, "status": "error", "error": str(e)})
                continue
        log.error(f"[AsyncFallbackChain] all {len(self.steps)} steps exhausted")
        if self.default is not None:
            return self.default
        raise FallbackExhausted(f"All {len(self.steps)} fallbacks exhausted")
