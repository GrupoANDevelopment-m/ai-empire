"""Verify that execute_tool() runs each namespaced tool exactly once.

A side-effect counter is injected into the resolved module, so a double
execution (dynamic registry + built-in registry, or a retry inside the
executor) would be caught.

Usage:  python3 tools_verify_single_exec.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from empire.agent.llm.dynamic_tools import resolve_tool_call
from empire.agent.llm.tools import execute_tool

# A tool with no external side effects and a harmless argument.
PROBE = "summarization__summarize"
PROBE_ARGS = {"text": "The quick brown fox jumps over the lazy dog."}


async def main() -> int:
    info = resolve_tool_call(PROBE)
    if info is None:
        print(f"FALHOU: {PROBE} não resolve no registro dinâmico")
        return 1

    calls = {"n": 0}
    original = info["func"]

    async def counting(*args, **kwargs):
        calls["n"] += 1
        return await original(*args, **kwargs)

    # The discovery registry is cached, so replacing the entry's callable
    # is what execute_tool() will pick up on its next resolution.
    # The wrapper must stay async, otherwise the executor would treat the
    # tool as synchronous and serialise an un-awaited coroutine.
    info["func"] = counting
    try:
        out = await execute_tool(PROBE, PROBE_ARGS)
        first = calls["n"]
        calls["n"] = 0
        await execute_tool(PROBE, PROBE_ARGS)
        second = calls["n"]
    finally:
        info["func"] = original

    print(f"execute_tool({PROBE!r})")
    print(f"  1ª chamada -> {first} execução(ões)")
    print(f"  2ª chamada -> {second} execução(ões)")
    print(f"  retorno: {str(out)[:120]}")

    ok = first == 1 and second == 1
    print("RESULTADO:", "OK — execução única" if ok
          else f"FALHOU — esperava 1, obtive {first}/{second}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
