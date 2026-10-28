"""summarize — real summarization (extractive + optional LLM abstractive)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _summarize import llm, sentences, tokenize, keywords, STOP


async def summarize(text: str, max_sentences: int = 5,
                    mode: str = "extractive") -> dict:
    """
    Summarize a text.

    Args:
        text: the input text
        max_sentences: how many sentences to keep (extractive)
        mode: "extractive" (TF-IDF sentence scoring, no LLM) or
              "abstractive" (LLM rewrites into new text)

    Returns:
        {"ok": True, "summary": str, "method": str, "compression": float}
    """
    if not text or len(text.strip()) < 20:
        raise ValueError("text too short to summarize (need 20+ chars)")

    sents = sentences(text)
    if not sents:
        raise ValueError("no sentences found")

    if mode == "abstractive":
        r = await llm(
            f"Summarize this text in at most {max_sentences} sentences. "
            f"Keep all key facts and numbers.\n\nTEXT:\n{text}",
            system="You produce faithful, concise summaries. Never invent facts.",
            max_tokens=800,
        )
        summary = r["text"]
        method = f"abstractive ({r['model']})"
    else:
        from collections import Counter
        freq = Counter(w for w in tokenize(text) if w not in STOP)
        scored = []
        for i, s in enumerate(sents):
            ws = tokenize(s)
            if not ws:
                continue
            score = sum(freq.get(w, 0) for w in ws) / (len(ws) ** 0.5)
            # position bonus: first and last sentences carry framing info
            if i == 0: score *= 1.5
            elif i == len(sents) - 1: score *= 1.25
            scored.append((score, i, s))
        scored.sort(reverse=True)
        keep = sorted(scored[:max_sentences], key=lambda t: t[1])
        summary = " ".join(s for _, _, s in keep)
        method = "extractive (tf-idf sentence scoring)"

    return {"ok": True, "summary": summary, "method": method,
            "sentences_in": len(sents), "sentences_out": len(sentences(summary)),
            "compression": round(1 - len(summary) / max(len(text), 1), 3),
            "keywords": keywords(text, 8)}
