"""Debug the ReAct loop: print the raw LLM response of every iteration.

Usage:  python3 tools_debug_react.py "sua pergunta"
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from empire.agent.llm import EmpireAgent


async def main(question: str) -> None:
    agent = EmpireAgent(tenant="default")
    original = agent.llm.chat
    calls = {"n": 0}

    async def traced(messages, tools=None, **kw):
        calls["n"] += 1
        resp = await original(messages, tools=tools, **kw)
        msg = resp.get("choices", [{}])[0].get("message", {})
        print(f"\n─── iteração {calls['n']} ───")
        print("  finish_reason:", resp.get("choices", [{}])[0].get("finish_reason"))
        print("  content len:", len(msg.get("content") or ""))
        print("  content:", json.dumps((msg.get("content") or "")[:400], ensure_ascii=False))
        tcs = msg.get("tool_calls")
        print("  tool_calls:", [t["function"]["name"] for t in tcs] if tcs else None)
        if calls["n"] > 1:
            last = messages[-1]
            print(f"  última msg: role={last.get('role')} len={len(str(last.get('content')))}")
        return resp

    agent.llm.chat = traced

    print(f"pergunta: {question}")
    async for ev in agent.stream(question, session="debug"):
        t = ev.get("type")
        if t == "text":
            print(f"\n[TEXT] {ev.get('content')}")
        elif t == "tool_call":
            print(f"[TOOL_CALL] {ev.get('tool')} {json.dumps(ev.get('args'), ensure_ascii=False)[:200]}")
        elif t == "tool_result":
            r = str(ev.get("result"))
            print(f"[TOOL_RESULT] {ev.get('tool')} -> {len(r)} chars")
        elif t == "error":
            print(f"[ERROR] {ev.get('text') or ev.get('error')}")
        else:
            print(f"[{t}] {json.dumps({k: v for k, v in ev.items() if k != 'type'}, ensure_ascii=False)[:200]}")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Pesquise na web as notícias mais recentes sobre Bitcoin e me diga o preço atual."
    asyncio.run(main(q))
