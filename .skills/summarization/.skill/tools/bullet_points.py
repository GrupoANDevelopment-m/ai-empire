"""bullet_points — real bullet-list conversion."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _summarize import sentences, keywords, STOP


async def bullet_points(text: str, max_bullets: int = 8,
                        extractive: bool = True) -> dict:
    """
    Turn text into a bullet list.

    Args:
        text: input text
        max_bullets: maximum bullets
        extractive: pick the most representative sentences (true)
                    or split on list markers/short clauses (false)

    Returns:
        {"ok": True, "bullets": [str], "count": int}
    """
    if not text or len(text.strip()) < 10:
        raise ValueError("text too short")
    import re

    if extractive:
        sents = sentences(text)
        from collections import Counter
        freq = Counter(w for w in re.findall(r"[\w']+", text.lower())
                       if w not in STOP and len(w) > 3)
        ranked = sorted(enumerate(sents), key=lambda t: -(
            sum(freq.get(w, 0) for w in re.findall(r"[\w']+", t[1].lower()))
            / max(len(t[1]), 1)))
        picks = sorted(ranked[:max_bullets], key=lambda t: t[0])
        bullets = [s for _, s in picks]
        method = "extractive tf-idf"
    else:
        bullets = []
        for line in text.splitlines():
            line = re.sub(r"^\s*([-*•]|\d+[.)])\s*", "", line).strip()
            if len(line) > 3:
                bullets.append(line)
            if len(bullets) >= max_bullets:
                break
        method = "markdown/list parsing"

    return {"ok": True, "bullets": bullets, "count": len(bullets),
            "method": method}
