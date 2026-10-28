"""extract_key_points — real key-point extraction."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _summarize import llm, sentences, keywords, STOP


async def extract_key_points(text: str, max_points: int = 7,
                             use_llm: bool = True) -> dict:
    """
    Extract the most important points as a list.

    Args:
        text: input text
        max_points: how many points
        use_llm: use the LLM (true) or TF-IDF sentence ranking (false)

    Returns:
        {"ok": True, "key_points": [str], "method": str}
    """
    if not text or len(text.strip()) < 20:
        raise ValueError("text too short")
    if use_llm:
        r = await llm(
            f"List the {max_points} most important points from this text as a "
            f"numbered list. One point per line, no preamble.\n\nTEXT:\n{text}",
            system="You extract factual key points. Be terse.",
            max_tokens=700,
        )
        pts = [l.strip(" -•\t") for l in r["text"].splitlines()
               if l.strip() and not l.strip().lower().startswith(("here", "the key"))]
        pts = [re.sub(r"^\d+[.)]\s*", "", p) for p in pts][:max_points]
        return {"ok": True, "key_points": pts, "count": len(pts),
                "method": f"llm ({r['model']})",
                "keywords": keywords(text, 10)}
    sents = sentences(text)
    from collections import Counter
    freq = Counter(w for w in __import__("re").findall(r"[\w']+", text.lower())
                   if w not in STOP and len(w) > 3)
    ranked = sorted(sents, key=lambda s: -(sum(freq.get(w, 0) for w in
                    __import__("re").findall(r"[\w']+", s.lower())) / max(len(s), 1)))
    return {"ok": True, "key_points": ranked[:max_points],
            "count": min(max_points, len(ranked)), "method": "tf-idf"}
import re
