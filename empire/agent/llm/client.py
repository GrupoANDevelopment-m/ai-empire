"""
LLM client — talks to Ollama (local), OpenAI, or Anthropic.
Uses native tool calling (OpenAI-compatible format).
Falls back to a small built-in heuristic only if NO LLM is available.
"""
from __future__ import annotations
import os
import json
import asyncio
import logging
import httpx
from typing import Any

log = logging.getLogger("empire.llm")


class LLMUnavailable(Exception):
    """Raised when no LLM is reachable."""


class LLMClient:
    """
    Single client that can talk to multiple backends.
    Detection order:
      1. OLLAMA_BASE_URL (default: http://localhost:11434) — local
      2. ANTHROPIC_API_KEY — Claude
      3. OPENAI_API_KEY — GPT
    Tool calling uses the OpenAI-compatible /v1/chat/completions endpoint,
    which Ollama, LiteLLM, vLLM, and others all support.
    """

    def __init__(self):
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL")  # explicit override, else auto-detect
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.litellm_url = os.getenv("LITELLM_URL", "http://localhost:4000").rstrip("/")
        self.openai_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
        self._backend: str | None = None
        self._available = False
        self._detected_model: str | None = None
        self._base_url: str | None = None

    async def detect(self) -> dict:
        """Probe each backend, return {backend, model, base_url, healthy}."""
        if self._backend:
            return {"backend": self._backend, "model": self._detected_model,
                    "base_url": self._base_url, "healthy": self._available}

        # 1. Ollama
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.ollama_url}/api/tags")
                if r.status_code == 200:
                    tags = r.json().get("models", [])
                    chosen = self.ollama_model
                    if not chosen:
                        preferred = ["qwen2.5", "qwen3", "llama3.1", "llama3.2", "mistral", "command-r"]
                        for p in preferred:
                            for m in tags:
                                if p in m.get("name", "").lower():
                                    chosen = m["name"]; break
                            if chosen: break
                    if not chosen and tags:
                        chosen = tags[0]["name"]
                    if chosen:
                        self._backend = "ollama"
                        self._detected_model = chosen
                        self._base_url = self.ollama_url
                        self._available = True
                        return {"backend": "ollama", "model": chosen, "base_url": self.ollama_url}
        except Exception as e:
            log.debug(f"Ollama not reachable: {e}")

        # 2. LiteLLM proxy (OpenAI-compatible)
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.litellm_url}/health/liveliness")
                if r.status_code in (200, 204):
                    self._backend = "litellm"
                    self._available = True
                    model = os.getenv("LITELLM_MODEL", "smart")
                    return {"backend": "litellm", "model": model, "base_url": self.litellm_url}
        except Exception:
            pass

        # 3. OpenAI direct
        if self.openai_key:
            self._backend = "openai"
            self._available = True
            return {"backend": "openai", "model": "gpt-4o-mini", "base_url": self.openai_url}

        # 4. Anthropic direct
        if self.anthropic_key:
            self._backend = "anthropic"
            self._available = True
            return {"backend": "anthropic", "model": "claude-sonnet-4-5", "base_url": "https://api.anthropic.com"}

        # Nothing available
        self._backend = "none"
        self._available = False
        return {"backend": "none", "model": None, "base_url": None, "healthy": False}

    @property
    def is_available(self) -> bool:
        return self._available and self._backend and self._backend != "none"

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
    ):
        """
        Chat completion. Returns ChatResponse.
        messages: [{"role": "user|assistant|system|tool", "content": "...", "tool_calls": ..., "tool_call_id": ...}]
        tools: OpenAI-format tool definitions
        """
        backend = (await self.detect())["backend"]

        if backend in ("ollama", "litellm", "openai"):
            return await self._openai_chat(
                backend, messages, tools, temperature, max_tokens, stream
            )
        if backend == "anthropic":
            return await self._anthropic_chat(messages, tools, temperature, max_tokens, stream)

        raise LLMUnavailable(
            "No LLM reachable. Start Ollama (the install.sh does this) or set ANTHROPIC_API_KEY / OPENAI_API_KEY in .env"
        )

    async def _openai_chat(self, backend, messages, tools, temperature, max_tokens, stream):
        """OpenAI-compatible chat (works with Ollama, LiteLLM, OpenAI)."""
        if backend == "ollama":
            url = f"{self.ollama_url}/v1/chat/completions"
            model = self._detected_model or self.ollama_model or "llama3.3"
            headers = {}
        elif backend == "litellm":
            url = f"{self.litellm_url}/v1/chat/completions"
            model = self._detected_model or os.getenv("LITELLM_MODEL", "smart")
            headers = {"Authorization": f"Bearer {os.getenv('LITELLM_MASTER_KEY', 'sk-empire-change-me')}"}
        else:  # openai
            url = f"{self.openai_url}/v1/chat/completions"
            model = self._detected_model or "gpt-4o-mini"
            headers = {"Authorization": f"Bearer {self.openai_key}"}

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if stream:
            return self._openai_stream(url, payload, headers)

        # 300s read timeout — large local models (qwen2.5:7b, llama3.1:8b) can be slow
        # on first inference while they load into memory.
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                raise Exception(f"LLM error {r.status_code}: {r.text[:300]}")
            return r.json()

    async def _openai_stream(self, url, payload, headers):
        """Yield chunks from a streaming response."""
        import json as _json
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as r:
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = _json.loads(data)
                        yield chunk
                    except _json.JSONDecodeError:
                        continue

    async def _anthropic_chat(self, messages, tools, temperature, max_tokens, stream):
        """Anthropic Messages API. Convert OpenAI-format to Anthropic-format."""
        # Extract system
        system = None
        msgs = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            elif m["role"] == "user":
                msgs.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                # Reconstruct tool_use blocks
                if m.get("tool_calls"):
                    content = []
                    if m.get("content"):
                        content.append({"type": "text", "text": m["content"]})
                    for tc in m["tool_calls"]:
                        content.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": _json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                        })
                    msgs.append({"role": "assistant", "content": content})
                else:
                    msgs.append({"role": "assistant", "content": m["content"]})
            elif m["role"] == "tool":
                msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                    }],
                })

        payload = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": msgs,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
            if r.status_code != 200:
                raise Exception(f"Anthropic error {r.status_code}: {r.text[:300]}")
            data = r.json()

        # Convert back to OpenAI-format for unified downstream handling
        return self._anthropic_to_openai(data)

    def _anthropic_to_openai(self, data: dict) -> dict:
        """Convert Anthropic response to OpenAI format."""
        content_blocks = data.get("content", [])
        text_parts = []
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })
        return {
            "id": data.get("id", ""),
            "model": data.get("model", "claude"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "".join(text_parts),
                    "tool_calls": tool_calls or None,
                },
                "finish_reason": data.get("stop_reason", "stop"),
            }],
            "usage": data.get("usage", {}),
        }


import json as _json  # used above
