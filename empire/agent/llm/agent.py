"""
The Empire Agent — a REAL LLM agent, not a bot.

Architecture:
  - User message → LLM (with system prompt + tools + history)
  - LLM decides: respond OR call tool(s)
  - If tool call: execute, send result back to LLM
  - LLM produces final natural-language answer
  - Stream tokens as they come

This is ReAct-style tool use, not pattern matching. The LLM decides.
"""
from __future__ import annotations
import json
import asyncio
import logging
import os
from typing import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from .client import LLMClient
from .tools import tool_definitions, execute_tool

log = logging.getLogger("empire.agent")


SYSTEM_PROMPT = """You are the AI Empire agent — a real AI that runs locally and can take actions.

You have access to 8 tools. Use them whenever the user asks you to do something
that requires them. Don't just talk about what you could do — actually call the tool.

Personality:
- Be friendly, direct, and concise
- Speak in the user's language (Portuguese, English, French, etc.)
- When you take an action, briefly explain what you're doing and why
- After a tool returns, synthesize the result into a clear answer
- If a tool fails, acknowledge it and suggest the next step
- Don't list your capabilities unless asked — just use them

Memory:
- You remember the entire conversation. Use context from earlier messages.
- When the user says "send an email to that lead" or "do the same for #2", refer back to earlier results.

When the user asks you to do something:
1. Decide which tool(s) to call (or if you just need to answer directly)
2. Call the tool(s) — the function will be executed and you'll get results back
3. Write a final answer that incorporates the results

Never invent tool results. If a tool errored, say so. If the user asks a
question you can answer without tools, just answer.

The user is talking to you in a terminal or web chat. Keep responses focused
and not too long unless they ask for detail.
"""


@dataclass
class Message:
    role: str  # user | assistant | system | tool
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class EmpireAgent:
    """
    Real LLM-backed agent with tool use, memory, and streaming.
    """

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()
        self.tools = tool_definitions()
        self.sessions: dict[str, list[Message]] = {}

    def _history(self, session: str) -> list[dict]:
        msgs = self.sessions.setdefault(session, [])
        # Convert to OpenAI format
        out = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in msgs:
            d = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            if m.name:
                d["name"] = m.name
            out.append(d)
        return out

    def _save(self, session: str, message: Message) -> None:
        self.sessions.setdefault(session, []).append(message)
        # Trim to last 40 messages to avoid context bloat
        if len(self.sessions[session]) > 40:
            self.sessions[session] = self.sessions[session][-40:]

    async def handle(self, text: str, session: str = "default") -> dict:
        """
        Non-streaming handle. Returns {text, tool_calls, model, backend}.
        """
        backend_info = await self.llm.detect()
        if not self.llm.is_available:
            return {
                "text": self._unavailable_message(backend_info),
                "tool_calls": [],
                "available": False,
                "backend": backend_info,
            }

        self._save(session, Message(role="user", content=text))
        messages = self._history(session)

        # Agent loop: keep calling LLM until it stops asking for tools
        all_tool_calls = []
        for iteration in range(6):  # max 6 tool-call rounds
            response = await self.llm.chat(messages, tools=self.tools)
            choice = response.get("choices", [{}])[0]
            msg = choice.get("message", {})
            text_reply = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls")

            # Save assistant message
            self._save(session, Message(
                role="assistant",
                content=text_reply,
                tool_calls=tool_calls,
            ))

            if not tool_calls:
                return {
                    "text": text_reply,
                    "tool_calls": all_tool_calls,
                    "available": True,
                    "backend": backend_info,
                    "model": response.get("model", "unknown"),
                }

            # Execute each tool call
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}
                log.info(f"Tool call: {fn_name}({fn_args})")
                result = await execute_tool(fn_name, fn_args)
                all_tool_calls.append({
                    "tool": fn_name,
                    "arguments": fn_args,
                    "result": result,
                })
                # Feed result back to LLM
                self._save(session, Message(
                    role="tool",
                    name=fn_name,
                    tool_call_id=tc["id"],
                    content=result,
                ))

            # Loop again with updated messages
            messages = self._history(session)

        # If we got here, we hit max iterations
        return {
            "text": "I got stuck in a tool loop. Let me know if you want me to try differently.",
            "tool_calls": all_tool_calls,
            "available": True,
            "backend": backend_info,
        }

    async def stream(self, text: str, session: str = "default") -> AsyncIterator[dict]:
        """
        Streaming handle. Yields {type, content|tool|args|result|...}.
        """
        backend_info = await self.llm.detect()
        if not self.llm.is_available:
            yield {
                "type": "error",
                "text": self._unavailable_message(backend_info),
                "backend": backend_info,
            }
            return

        self._save(session, Message(role="user", content=text))
        messages = self._history(session)

        # Non-streaming tool call round (LLMs vary in streaming tool support)
        for iteration in range(6):
            response = await self.llm.chat(messages, tools=self.tools)
            choice = response.get("choices", [{}])[0]
            msg = choice.get("message", {})
            text_reply = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls")

            self._save(session, Message(
                role="assistant",
                content=text_reply,
                tool_calls=tool_calls,
            ))

            if not tool_calls:
                if text_reply:
                    yield {"type": "text", "content": text_reply}
                yield {
                    "type": "done",
                    "model": response.get("model", "unknown"),
                    "backend": backend_info,
                }
                return

            # Show tool calls in stream
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}
                yield {"type": "tool_call", "tool": fn_name, "args": fn_args}

                result = await execute_tool(fn_name, fn_args)
                yield {"type": "tool_result", "tool": fn_name, "result": result}

                self._save(session, Message(
                    role="tool",
                    name=fn_name,
                    tool_call_id=tc["id"],
                    content=result,
                ))
            messages = self._history(session)

        yield {"type": "done"}

    def clear_session(self, session: str) -> None:
        self.sessions.pop(session, None)

    def _unavailable_message(self, backend: dict) -> str:
        return (
            "⚠️  No LLM reachable. I need an LLM to actually think.\n\n"
            "Quickest fix — start Ollama (the install.sh does this):\n"
            "  ./install.sh\n\n"
            "Or set an API key in .env:\n"
            "  ANTHROPIC_API_KEY=sk-...   (Claude — best quality)\n"
            "  OPENAI_API_KEY=sk-...      (GPT)\n\n"
            f"Probed: {backend}"
        )
