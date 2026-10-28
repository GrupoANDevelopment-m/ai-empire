"""translate — real translation via the configured LLM."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _translate import llm_translate


async def translate(text: str, target_language: str = "English",
                    source_language: str = None,
                    preserve_formatting: bool = True) -> dict:
    """
    Translate text into another language.

    Args:
        text: the text to translate
        target_language: target language name or code (e.g. "Spanish", "pt-BR")
        source_language: source language, or None to auto-detect
        preserve_formatting: keep markdown/line breaks

    Returns:
        {"ok": True, "translation": str, "model": str, "chars": int}
    """
    if not text or not text.strip():
        raise ValueError("text cannot be empty")
    r = await llm_translate(text, target_language, source_language)
    return {"ok": True, "translation": r["text"], "model": r["model"],
            "backend": r["backend"], "source": source_language or "auto",
            "target": target_language, "chars": len(r["text"]),
            "tokens": (r.get("usage") or {}).get("total_tokens")}
