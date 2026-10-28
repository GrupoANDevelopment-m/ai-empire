"""batch_translate — translate many strings concurrently."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _translate import llm_translate


async def batch_translate(texts: list, target_language: str = "English",
                          source_language: str = None,
                          concurrency: int = 5) -> dict:
    """
    Translate a list of strings.

    Args:
        texts: list of strings to translate
        target_language: target language
        source_language: source language or auto
        concurrency: parallel requests (default 5)

    Returns:
        {"ok": True, "results": [...], "count": int, "errors": int}
    """
    if not texts:
        raise ValueError("texts cannot be empty")
    if not isinstance(texts, list):
        raise ValueError("texts must be a list of strings")

    sem = asyncio.Semaphore(concurrency)
    results = [None] * len(texts)
    errors = 0

    async def one(i, t):
        nonlocal errors
        async with sem:
            try:
                r = await llm_translate(t, target_language, source_language)
                results[i] = {"index": i, "original": t,
                              "translation": r["text"], "ok": True}
            except Exception as e:
                errors += 1
                results[i] = {"index": i, "original": t, "ok": False,
                              "error": f"{type(e).__name__}: {str(e)[:120]}"}

    await asyncio.gather(*(one(i, t) for i, t in enumerate(texts)))
    ok = sum(1 for r in results if r["ok"])
    first_error = next((r.get("error") for r in results
                        if r.get("error")), None)
    # ok is False when *nothing* was translated — a batch that translated
    # zero strings must never be reported as a success.
    return {"ok": ok > 0, "count": len(texts), "translated": ok,
            "errors": errors, "target": target_language, "results": results,
            **({"error": first_error} if ok == 0 and first_error else {})}
