"""
AI Gateway client — unified interface over OmniRoute / LiteLLM / direct providers.
Auto-detects available gateway, applies circuit breaker + retry + fallback.

Priority:
  1. LiteLLM proxy (if LITELLM_URL is set and reachable)
  2. OmniRoute (if OMNIROUTE_URL is set and reachable)
  3. Direct provider (Ollama, Anthropic, OpenAI based on env)
"""
from __future__ import annotations
import os
import json
import logging
import asyncio
import httpx
from typing import Any
from dataclasses import dataclass, field

from .circuit_breaker import CircuitBreaker, CircuitOpenError
from .retry import (
    retry_with_backoff, async_retry_with_backoff,
    RetryableError, NonRetryableError, classify_http_error,
)
from .fallback import AsyncFallbackChain, FallbackStep

log = logging.getLogger("empire.gateway")

GATEWAY_TIMEOUT = 120.0


class GatewayError(Exception):
    """Generic gateway error."""


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class ChatResponse:
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    provider: str = ""  # which gateway/provider served this


class AIGateway:
    """
    Unified AI Gateway client. Wraps LiteLLM, OmniRoute, or direct providers
    with circuit breaker + retry + fallback built-in.

    Usage:
        gw = AIGateway()
        resp = await gw.chat([
            ChatMessage(role="user", content="Hello"),
        ], model="auto")
        print(resp.content)
    """

    def __init__(
        self,
        litellm_url: str | None = None,
        omniroute_url: str | None = None,
        anthropic_key: str | None = None,
        openai_key: str | None = None,
        ollama_url: str | None = None,
    ):
        self.litellm_url = litellm_url or os.getenv("LITELLM_URL", "http://litellm-proxy:4000")
        self.omniroute_url = omniroute_url or os.getenv("OMNIROUTE_URL", "http://omniroute:20128")
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY", "")
        self.ollama_url = ollama_url or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

        # Per-gateway circuit breakers
        self.breakers = {
            "litellm": CircuitBreaker("litellm", failure_threshold=5, recovery_timeout=30),
            "omniroute": CircuitBreaker("omniroute", failure_threshold=5, recovery_timeout=30),
            "anthropic": CircuitBreaker("anthropic", failure_threshold=3, recovery_timeout=60),
            "openai": CircuitBreaker("openai", failure_threshold=3, recovery_timeout=60),
            "ollama": CircuitBreaker("ollama", failure_threshold=10, recovery_timeout=15),
        }

        self.stats_total = 0
        self.stats_errors = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        prefer: list[str] | None = None,
    ) -> ChatResponse:
        """
        Chat completion via the gateway.

        `model` can be:
          - "auto": gateway picks best available
          - "fast" / "smart": LiteLLM routing alias
          - explicit model name: "claude-sonnet-4-5", "gpt-4o", "llama3.3"
        """
        if prefer is None:
            prefer = ["litellm", "omniroute", "anthropic", "openai", "ollama"]

        chain = AsyncFallbackChain()
        for backend in prefer:
            if backend == "litellm":
                chain.add(FallbackStep("litellm", self._call_litellm, kwargs={
                    "messages": messages, "model": model,
                    "temperature": temperature, "max_tokens": max_tokens,
                }))
            elif backend == "omniroute":
                chain.add(FallbackStep("omniroute", self._call_omniroute, kwargs={
                    "messages": messages, "model": model,
                    "temperature": temperature, "max_tokens": max_tokens,
                }))
            elif backend == "anthropic" and self.anthropic_key:
                chain.add(FallbackStep("anthropic", self._call_anthropic_direct, kwargs={
                    "messages": messages, "model": model,
                    "temperature": temperature, "max_tokens": max_tokens,
                }))
            elif backend == "openai" and self.openai_key:
                chain.add(FallbackStep("openai", self._call_openai_direct, kwargs={
                    "messages": messages, "model": model,
                    "temperature": temperature, "max_tokens": max_tokens,
                }))
            elif backend == "ollama":
                chain.add(FallbackStep("ollama", self._call_ollama_direct, kwargs={
                    "messages": messages, "model": model,
                    "temperature": temperature, "max_tokens": max_tokens,
                }))

        try:
            return await chain.run()
        except Exception as e:
            self.stats_errors += 1
            log.error(f"All gateway backends failed: {e}")
            # Return a graceful degraded response
            return ChatResponse(
                content="[Service temporarily degraded] All AI providers unavailable. Please try again shortly.",
                model="degraded",
                provider="none",
                raw={"error": str(e), "attempts": chain.attempts},
            )

    # ---- Backend implementations ----
    async def _call_litellm(self, messages, model, temperature, max_tokens) -> ChatResponse:
        """Call LiteLLM proxy (OpenAI-compatible)."""
        breaker = self.breakers["litellm"]
        if breaker.is_open:
            raise CircuitOpenError("litellm", breaker._seconds_until_recovery())

        payload = {
            "model": model if model not in ("auto",) else "gpt-4o-mini",
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self.litellm_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('LITELLM_MASTER_KEY', 'sk-empire-change-me')}",
        }

        async def _do():
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504, 529):
                    raise RetryableError(f"LiteLLM {r.status_code}: {r.text[:200]}")
                if r.status_code in (401, 403, 404, 422):
                    raise NonRetryableError(f"LiteLLM {r.status_code}: {r.text[:200]}")
                if r.status_code != 200:
                    raise RetryableError(f"LiteLLM {r.status_code}: {r.text[:200]}")
                data = r.json()
                return ChatResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", model),
                    usage=data.get("usage", {}),
                    raw=data,
                    provider="litellm",
                )

        return await breaker.async_call(_do)

    async def _call_omniroute(self, messages, model, temperature, max_tokens) -> ChatResponse:
        """Call OmniRoute (OpenAI-compatible)."""
        breaker = self.breakers["omniroute"]
        if breaker.is_open:
            raise CircuitOpenError("omniroute", breaker._seconds_until_recovery())

        payload = {
            "model": model if model not in ("auto",) else "gpt-4o-mini",
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = f"{self.omniroute_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('OMNIROUTE_KEY', 'empire')}",
        }

        async def _do():
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RetryableError(f"OmniRoute {r.status_code}")
                if r.status_code in (401, 403, 404):
                    raise NonRetryableError(f"OmniRoute {r.status_code}")
                if r.status_code != 200:
                    raise RetryableError(f"OmniRoute {r.status_code}: {r.text[:200]}")
                data = r.json()
                return ChatResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", model),
                    raw=data,
                    provider="omniroute",
                )

        return await breaker.async_call(_do)

    async def _call_anthropic_direct(self, messages, model, temperature, max_tokens) -> ChatResponse:
        """Direct Anthropic API."""
        breaker = self.breakers["anthropic"]
        if breaker.is_open:
            raise CircuitOpenError("anthropic", breaker._seconds_until_recovery())

        system = next((m.content for m in messages if m.role == "system"), None)
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        payload = {
            "model": model if not model.startswith("claude") else model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_msgs,
        }
        if system:
            payload["system"] = system
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async def _do():
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504, 529):
                    raise RetryableError(f"Anthropic {r.status_code}")
                if r.status_code in (401, 403, 404):
                    raise NonRetryableError(f"Anthropic {r.status_code}")
                if r.status_code != 200:
                    raise RetryableError(f"Anthropic {r.status_code}: {r.text[:200]}")
                data = r.json()
                return ChatResponse(
                    content=data["content"][0]["text"],
                    model=data.get("model", model),
                    usage=data.get("usage", {}),
                    raw=data,
                    provider="anthropic",
                )

        return await breaker.async_call(_do)

    async def _call_openai_direct(self, messages, model, temperature, max_tokens) -> ChatResponse:
        """Direct OpenAI API."""
        breaker = self.breakers["openai"]
        if breaker.is_open:
            raise CircuitOpenError("openai", breaker._seconds_until_recovery())

        payload = {
            "model": model if not model.startswith("gpt") else model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }

        async def _do():
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RetryableError(f"OpenAI {r.status_code}")
                if r.status_code in (401, 403, 404):
                    raise NonRetryableError(f"OpenAI {r.status_code}")
                if r.status_code != 200:
                    raise RetryableError(f"OpenAI {r.status_code}: {r.text[:200]}")
                data = r.json()
                return ChatResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=data.get("model", model),
                    usage=data.get("usage", {}),
                    raw=data,
                    provider="openai",
                )

        return await breaker.async_call(_do)

    async def _call_ollama_direct(self, messages, model, temperature, max_tokens) -> ChatResponse:
        """Direct Ollama (always available locally)."""
        breaker = self.breakers["ollama"]
        if breaker.is_open:
            raise CircuitOpenError("ollama", breaker._seconds_until_recovery())

        ollama_model = "llama3.3" if model in ("auto", "fast", "smart") else model
        payload = {
            "model": ollama_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        url = f"{self.ollama_url}/api/chat"

        async def _do():
            async with httpx.AsyncClient(timeout=GATEWAY_TIMEOUT) as client:
                r = await client.post(url, json=payload)
                if r.status_code != 200:
                    raise RetryableError(f"Ollama {r.status_code}: {r.text[:200]}")
                data = r.json()
                return ChatResponse(
                    content=data.get("message", {}).get("content", ""),
                    model=ollama_model,
                    raw=data,
                    provider="ollama",
                )

        return await breaker.async_call(_do)

    def get_health(self) -> dict:
        """Health snapshot of all backends."""
        return {
            "backends": {name: b.stats() for name, b in self.breakers.items()},
            "stats": {"total": self.stats_total, "errors": self.stats_errors},
        }
