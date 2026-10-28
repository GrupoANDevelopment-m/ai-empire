"""detect_language — real language detection via langid + LLM fallback."""
import sys, os


async def detect_language(text: str) -> dict:
    """
    Detect the language of a text.

    Args:
        text: sample text (10+ chars works best)

    Returns:
        {"ok": True, "language": str, "code": str, "confidence": float}
    """
    if not text or len(text.strip()) < 2:
        raise ValueError("text too short to detect")
    sample = text[:2000]

    # Primary: langid (offline, fast)
    try:
        from langid import classify
        code, raw = classify(sample)
        # langid returns a negative log-probability. Absolute value is a
        # poor scale, so score by margin against the runner-up language.
        try:
            from langid.langid import rank
            ranked = rank(sample)
            top_c, top_s = ranked[0]
            second_s = ranked[1][1] if len(ranked) > 1 else 0.0
            margin = abs(top_s - second_s)
            conf = max(0.0, min(1.0, margin * 4.0))
        except Exception:
            conf = 0.5
        names = {"pt": "Portuguese", "en": "English", "es": "Spanish",
                 "fr": "French", "de": "German", "it": "Italian",
                 "ja": "Japanese", "ko": "Korean", "zh-cn": "Chinese",
                 "ru": "Russian", "mk": "Macedonian", "bg": "Bulgarian", "ar": "Arabic", "nl": "Dutch"}
        return {"ok": True, "language": names.get(code, code), "code": code,
                "confidence": round(float(conf), 4), "method": "langid"}
    except ImportError:
        pass

    # Fallback: Unicode script + stopword profile for Latin-script languages.
    # A script alone cannot tell Portuguese from English, so Latin text is
    # additionally scored against per-language stopword sets.
    import unicodedata as ud
    scripts = {}
    for ch in sample:
        if not ch.isalpha():
            continue
        name = ud.name(ch, "")
        s = ("LATIN" if "LATIN" in name else
             "CYRILLIC" if "CYRILLIC" in name else
             "ARABIC" if "ARABIC" in name else
             "CJK" if "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name else
             "OTHER")
        scripts[s] = scripts.get(s, 0) + 1
    top = max(scripts, key=scripts.get) if scripts else "UNKNOWN"
    total = sum(scripts.values()) or 1

    if top == "LATIN":
        lang, code, hits = _latin_language(sample)
        return {"ok": True, "language": lang, "code": code,
                "confidence": round(hits, 3), "method": "stopword-profile",
                "scripts": scripts, "matched_tokens": int(hits * total)}

    guess = {"LATIN": ("Unknown (Latin script)", "und"),
             "CYRILLIC": ("Russian", "ru"),
             "ARABIC": ("Arabic", "ar"),
             "CJK": ("Japanese/Chinese", "ja"),
             "OTHER": ("Unknown", "und")}[top]
    return {"ok": True, "language": guess[0], "code": guess[1],
            "confidence": round(scripts.get(top, 0) / total, 3),
            "method": "unicode-heuristic",
            "scripts": scripts}


# Function words that reliably indicate a Latin-script language.
_STOPWORDS = {
    "pt": {"de", "que", "não", "para", "com", "uma", "os", "as", "do", "da",
           "no", "na", "por", "mais", "como", "mas", "foi", "ele", "você",
           "está", "são", "meu", "muito", "quando", "também", "só", "ou",
           "porque", "então", "já", "é", "à", "pelo", "pela"},
    "en": {"the", "and", "of", "to", "in", "is", "it", "you", "that", "for",
           "on", "with", "as", "at", "by", "this", "be", "are", "was", "not",
           "but", "have", "from", "or", "an", "we", "they", "he", "she",
           "what", "which", "how", "would", "could", "should", "will"},
    "es": {"de", "que", "la", "el", "en", "los", "del", "se", "las", "por",
           "un", "para", "con", "no", "una", "su", "al", "lo", "como", "más",
           "pero", "sus", "le", "ya", "o", "este", "porque", "cuando",
           "muy", "sin", "sobre", "también", "me", "hasta", "hay", "donde"},
    "fr": {"le", "de", "un", "être", "et", "à", "il", "avoir", "ne", "je",
           "son", "que", "se", "qui", "ce", "dans", "en", "du", "elle", "au",
           "pour", "pas", "vous", "par", "sur", "faire", "plus", "me", "on",
           "mon", "tu", "nous", "comme", "mais", "des", "est"},
    "it": {"di", "che", "il", "la", "e", "per", "un", "in", "è", "non",
           "una", "sono", "con", "si", "come", "del", "da", "più", "ma",
           "questo", "anche", "sono", "come", "quando", "perché", "se",
           "più", "molto", "gli", "dei", "nel", "alla", "della", "sono"},
    "de": {"der", "die", "und", "in", "den", "von", "zu", "das", "mit",
           "sich", "des", "auf", "für", "ist", "im", "dem", "nicht", "ein",
           "eine", "als", "auch", "es", "an", "werden", "aus", "er", "hat",
           "dass", "sie", "nach", "wird", "bei", "einer", "um", "am", "den"},
}
_LANG_NAMES = {"pt": "Portuguese", "en": "English", "es": "Spanish",
               "fr": "French", "it": "Italian", "de": "German"}


def _latin_language(sample: str) -> tuple[str, str, float]:
    """Score Latin-script text against per-language stopword sets.

    Returns (language_name, code, confidence 0..1).
    """
    import re
    import unicodedata as ud

    def norm(tok: str) -> str:
        # strip accents so "cómo" matches the stopword "como"
        return "".join(c for c in ud.normalize("NFD", tok)
                       if ud.category(c) != "Mn")

    words = [norm(w.lower()) for w in re.findall(r"[a-zA-ZÀ-ÿ']+", sample)]
    words = [w for w in words if w]
    if not words:
        return ("Unknown (Latin script)", "und", 0.0)
    scores = {}
    for code, stops in _STOPWORDS.items():
        scores[code] = sum(1 for w in words if w in stops)
    best = max(scores, key=scores.get)
    hits = scores[best]
    if hits == 0:
        return ("Unknown (Latin script)", "und", 0.0)
    # confidence = share of tokens explained, tempered by absolute hit count
    share = hits / len(words)
    strength = min(1.0, hits / 4.0)
    runner = sorted(scores.values(), reverse=True)
    margin = (runner[0] - (runner[1] if len(runner) > 1 else 0)) / max(runner[0], 1)
    conf = max(0.0, min(1.0, 0.5 * share + 0.3 * strength + 0.2 * margin))
    return (_LANG_NAMES[best], best, round(conf, 3))
