"""generate_tldr — one-sentence TL;DR."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _summarize import llm, sentences


async def generate_tldr(text: str, max_chars: int = 280) -> dict:
    """
    Produce a TL;DR of the text in one sentence.

    Args:
        text: input text
        max_chars: hard cap on the TL;DR length

    Returns:
        {"ok": True, "tldr": str, "chars": int}
    """
    if not text or len(text.strip()) < 20:
        raise ValueError("text too short")
    r = await llm(
        f"Write a single-sentence TL;DR of at most {max_chars} characters "
        f"for this text. No preamble, just the sentence.\n\nTEXT:\n{text}",
        system="You write precise one-sentence summaries.",
        max_tokens=200,
    )
    tldr = r["text"].strip().strip('"').split("\n")[0]
    if len(tldr) > max_chars:
        tldr = tldr[:max_chars - 1].rsplit(" ", 1)[0] + "…"
    return {"ok": True, "tldr": tldr, "chars": len(tldr),
            "method": f"llm ({r['model']})"}
