# ADR-0004: Use Bleach for HTML Sanitization

## Status
Accepted — 2026-02-15

## Context
User-generated content (chat messages, file uploads) may contain HTML.
We need to sanitize before storing or rendering. Options:
1. **html.escape()** — too aggressive, breaks legitimate HTML
2. **lxml.clean** — flexible but unmaintained
3. **nh3** — Rust-based, fast, modern
4. **bleach** — Mozilla-maintained, 10+ years in production

## Decision
**Use bleach** with conservative default policy.

## Rationale
- Mozilla production-grade (used in Mozilla Add-ons, Pocket, etc.)
- Whitelist-based: explicitly allow what we want
- Strips `<script>`, `javascript:`, event handlers
- **Tested: `<script>` stripped, `javascript:` blocked**

## Configuration
```python
bleach.clean(
    text,
    tags=['b', 'i', 'em', 'strong', 'a', 'code', 'pre', 'p', 'br'],
    attributes={'a': ['href', 'title']},
    protocols=['http', 'https', 'mailto'],
    strip=True,
)
```

## Consequences
**Positive:**
- XSS protection by default
- 10+ years of CVE fixes
- Easy to test

**Negative:**
- Adds 200KB dependency
- Conservative defaults may break some user content
