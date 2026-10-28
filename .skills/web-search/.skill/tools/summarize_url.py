"""summarize_url — real fetch + LLM summary of a single page."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util


def _load(name):
    s = importlib.util.spec_from_file_location("ws2_" + name,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py"))
    m = importlib.util.module_from_spec(s); sys.modules["ws2_" + name] = m
    s.loader.exec_module(m)
    return m


async def summarize_url(url: str, max_words: int = 200,
                        focus: str = None) -> dict:
    """
    Fetch a URL and summarize it.

    Args:
        url: page to read
        max_words: target summary length
        focus: optional angle, e.g. "the pricing section"

    Returns:
        {"ok": True, "title": str, "url": str, "summary": str, "model": str}
    """
    ext = _load("extract_text")
    page = await ext.extract_text(url, max_chars=20000)
    if not page.get("ok") and not page.get("text"):
        return {"ok": False, "url": url, "error": page.get("error", "fetch failed")}

    text = page.get("text", "")
    if not text.strip():
        return {"ok": False, "url": url, "error": "no extractable text"}

    summary, model = "", None
    try:
        sys.path.insert(0, "/workspace/ai-empire")
        from empire.agent.llm.client import LLMClient
        c = LLMClient()
        if not c.is_available:
            await c.detect()
        if c.is_available:
            focus_txt = f" Focus on: {focus}." if focus else ""
            r = await c.chat(
                messages=[
                    {"role": "system", "content":
                     "You summarize web pages accurately and concisely."},
                    {"role": "user", "content":
                     f"Summarize this page in about {max_words} words.{focus_txt}\n\n"
                     f"TITLE: {page.get('title','')}\n\n{text}"},
                ], temperature=0.3, max_tokens=1400)
            summary = r["choices"][0]["message"]["content"] or ""
            model = r.get("model")
    except Exception:
        pass

    if not summary:
        summary = text[: max_words * 6]

    return {"ok": True, "url": url, "title": page.get("title", ""),
            "summary": summary.strip(), "model": model,
            "source_words": page.get("words", 0),
            "fallback": model is None}
