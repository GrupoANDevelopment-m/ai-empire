"""
PII redaction — patterns to detect and redact personally identifiable
information before logging, audit, or persisting to vector DB.

Configurable via PII_REDACT env var (comma-separated list of pattern names).
Default patterns: email, phone, credit_card, ssn (US), iban, ipv4.

Usage:
    from empire.security.pii import redact
    safe_text = redact("Contact me at john@example.com or +1-555-1234")

For production, also consider:
  - Microsoft Presidio (https://github.com/microsoft/presidio)
  - Hugging Face PII detection models
"""
import os
import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class PIIPattern:
    name: str
    regex: re.Pattern
    replacement: str = "[REDACTED-{name}]"


_PATTERNS = {
    "email":      PIIPattern("EMAIL",     re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    "phone":      PIIPattern("PHONE",     re.compile(r"\+?\d{1,3}?[ .-]?\(?\d{2,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}")),
    "credit_card":PIIPattern("CC",        re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
    "ssn":        PIIPattern("SSN",       re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    "iban":       PIIPattern("IBAN",      re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    "ipv4":       PIIPattern("IPV4",      re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    "url_token":  PIIPattern("API_KEY",   re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})")),
}


def _enabled() -> dict[str, PIIPattern]:
    raw = os.getenv("PII_REDACT", "email,phone,credit_card,ssn,iban,ipv4")
    enabled = {n.strip() for n in raw.split(",") if n.strip()}
    return {k: v for k, v in _PATTERNS.items() if k in enabled}


_REDACTORS: dict[str, PIIPattern] = _enabled()


def redact(text: str, custom: list[PIIPattern] | None = None) -> str:
    """Apply all enabled PII patterns to the text. Returns redacted string."""
    if not text:
        return text
    out = text
    patterns = list(_REDACTORS.values())
    if custom:
        patterns += custom
    for p in patterns:
        out = p.regex.sub(p.replacement.format(name=p.name), out)
    return out


class PIIRedactor:
    """Stateful redactor — allows adding runtime patterns (e.g., from config)."""
    def __init__(self):
        self.patterns: list[PIIPattern] = list(_REDACTORS.values())

    def add(self, name: str, regex: str, replacement: str | None = None):
        rep = replacement or f"[REDACTED-{name.upper()}]"
        self.patterns.append(PIIPattern(name.upper(), re.compile(regex), rep))

    def redact(self, text: str) -> str:
        out = text
        for p in self.patterns:
            out = p.regex.sub(p.replacement.format(name=p.name), out)
        return out
