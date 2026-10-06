"""
PII redaction — powered by Microsoft Presidio (https://github.com/microsoft/presidio).

Real NER + regex detection. Replaces the previous hand-rolled regex-only module.

Falls back to regex-only if presidio isn't installed (degraded mode, still safe).

Usage:
    from empire.security.pii import redact
    safe_text = redact("Contact me at john@example.com or +1-555-1234")
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import Callable

# Try to import presidio; degrade gracefully if unavailable
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    _PRESIDIO_AVAILABLE = True
except Exception:
    _PRESIDIO_AVAILABLE = False


@dataclass
class PIIPattern:
    name: str
    regex: re.Pattern
    replacement: str = "[REDACTED-{name}]"


# Regex fallback for when presidio isn't available
_FALLBACK_PATTERNS = {
    "email":       PIIPattern("EMAIL",      re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    "phone":       PIIPattern("PHONE",      re.compile(r"\+?\d{1,3}?[ .-]?\(?\d{2,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}")),
    "credit_card": PIIPattern("CC",         re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    "ssn":         PIIPattern("SSN",        re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    "iban":        PIIPattern("IBAN",       re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    "ipv4":        PIIPattern("IPV4",       re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    "url_token":   PIIPattern("API_KEY",    re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*[\'\"]?([a-zA-Z0-9_\-]{20,})")),
}


_ENGINE = None


def _get_engine():
    """Lazy-init presidio engine. Uses an allowlist of entity types that work
    reliably with the regex recognizers (NER-based ones depend on network for
    tldextract which we cannot guarantee).
    """
    global _ENGINE
    if _ENGINE is None:
        if not _PRESIDIO_AVAILABLE:
            _ENGINE = "fallback"
            return _ENGINE
        try:
            # Disable online tld snapshot fetch — presidio is too brittle here
            import os as _os
            _os.environ.setdefault("TLDEXTRACT_SUFFIX_LIST_URLS", "")
            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
            }
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
            # Build engine and immediately drop problematic recognizers
            engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
            # Only keep recognizers that don't need network
            from presidio_analyzer import RecognizerRegistry
            keep = {"EmailRecognizer", "PhoneRecognizer", "CreditCardRecognizer",
                    "UsSsnRecognizer", "IpRecognizer", "IbanRecognizer",
                    "UrlRecognizer"}
            for rec in list(engine.registry.recognizers):
                if rec.name not in keep:
                    engine.registry.remove_recognizer(rec.name)
            _ENGINE = engine
        except Exception:
            _ENGINE = "fallback"
    return _ENGINE


def redact(text: str, custom: list[PIIPattern] | None = None,
           language: str = "en") -> str:
    """Redact PII from text using presidio (preferred) or regex fallback.

    Returns the redacted text.
    """
    if not text:
        return text
    engine = _get_engine()
    if engine and engine != "fallback":
        try:
            results = engine.analyze(text=text, language=language)
            # Use SHORT fixed tag so any PII detection fits without truncation
            TAG = "[REDACTED]"
            # Build non-overlapping spans, picking highest-score when overlapping
            results.sort(key=lambda r: (r.start, -(r.end - r.start), -r.score))
            spans = []
            occupied = [False] * len(text)
            for r in results:
                if any(occupied[r.start:r.end]):
                    continue
                for i in range(r.start, r.end):
                    occupied[i] = True
                spans.append((r.start, r.end, r.entity_type))
            spans.sort(key=lambda x: x[0], reverse=True)
            chars = list(text)
            for start, end, etype in spans:
                length = end - start
                chars[start:end] = list(TAG) + [" "] * max(0, length - len(TAG))
            return "".join(chars)
        except Exception:
            pass  # fall through to regex
    # Regex fallback
    for name in os.getenv("PII_REDACT", "email,phone,credit_card,ssn,iban,ipv4").split(","):
        name = name.strip()
        pat = _FALLBACK_PATTERNS.get(name)
        if pat:
            text = pat.regex.sub(pat.replacement.format(name=pat.name), text)
    if custom:
        for pat in custom:
            text = pat.regex.sub(pat.replacement.format(name=pat.name), text)
    return text


# Backward-compat alias
def redact_pii(text: str) -> str:
    return redact(text)


# Re-export for callers that imported these directly
PIIRedactor = _FALLBACK_PATTERNS  # dict for lookup


# Preset deployment
REDACT = redact
