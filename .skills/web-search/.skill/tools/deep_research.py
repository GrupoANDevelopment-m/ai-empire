"""deep_research — multi-source real research pipeline."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util


def _load(name):
    s = importlib.util.spec_from_file_location("ws_" + name,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py"))
    m = importlib.util.module_from_spec(s); sys.modules["ws_" + name] = m
    s.loader.exec_module(m)
    return m


async def deep_research(topic: str, num_sources: int = 5,
                        fetch_full_text: bool = True) -> dict:
    """
    Research a topic: search the web, fetch sources, synthesize with the LLM.

    Args:
        topic: research question
        num_sources: how many pages to read
        fetch_full_text: fetch each result's page content

    Returns:
        {"ok": True, "topic": str, "synthesis": str, "sources": [...]}
    """
    if not topic.strip():
        raise ValueError("topic cannot be empty")

    search = _load("search")
    sr = await search.search(topic, limit=num_sources * 2)
    if not sr.get("ok") or not sr.get("results"):
        return {"ok": False, "topic": topic, "error": sr.get("error", "no results"),
                "sources": []}

    cands = [r for r in sr["results"] if r.get("url")][:num_sources]
    sources = []
    if fetch_full_text:
        extract = _load("extract_text")
        sem = asyncio.Semaphore(5)

        async def read(c):
            async with sem:
                try:
                    t = await extract.extract_text(c["url"], max_chars=6000)
                    return {**c, "title": t.get("title") or c.get("title"),
                            "excerpt": t.get("text", "")[:1800],
                            "read_ok": t.get("ok", False)}
                except Exception as e:
                    return {**c, "excerpt": "", "read_ok": False,
                            "error": f"{type(e).__name__}: {str(e)[:80]}"}
        sources = await asyncio.gather(*(read(c) for c in cands))
    else:
        sources = [{**c, "excerpt": c.get("snippet", "")} for c in cands]

    corpus = "\n\n---\n\n".join(
        f"[{i+1}] {s.get('title') or s.get('url')}\n{s.get('excerpt','')}"
        for i, s in enumerate(sources) if s.get("excerpt"))

    synthesis = ""
    model = None
    try:
        sys.path.insert(0, "/workspace/ai-empire")
        from empire.agent.llm.client import LLMClient
        c = LLMClient()
        if not c.is_available:
            await c.detect()
        if c.is_available:
            r = await c.chat(
                messages=[
                    {"role": "system", "content":
                     "You synthesize research from multiple sources. Cite with "
                     "[n] markers. Note disagreements. Never invent facts."},
                    {"role": "user", "content":
                     f"Research topic: {topic}\n\nSOURCES:\n{corpus}\n\n"
                     f"Write a structured synthesis with key findings and citations."},
                ], temperature=0.3, max_tokens=2000)
            synthesis = r["choices"][0]["message"]["content"] or ""
            model = r.get("model")
    except Exception:
        pass

    return {"ok": True, "topic": topic, "engine": sr.get("engine"),
            "sources_read": sum(1 for s in sources if s.get("read_ok")),
            "sources": sources, "synthesis": synthesis,
            "synthesis_model": model,
            "note": "" if synthesis else "LLM unavailable — returning sources only"}
