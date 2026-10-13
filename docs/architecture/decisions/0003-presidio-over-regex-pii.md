# ADR-0003: Use Presidio for PII Detection Instead of Regex

## Status
Accepted — 2026-02-10

## Context
We need to detect and redact PII in user messages and logs. Options:
1. **Hand-rolled regex** — fast, but misses context
2. **Presidio (Microsoft)** — NER + custom recognizers
3. **Comprehend (AWS)** — managed, but vendor lock-in
4. **spaCy NER** — fast, but needs custom recognizers

## Decision
**Use Presidio** with spaCy backend + custom recognizers for PT-BR patterns.

## Rationale
- Microsoft production-grade, used in Dynamics 365
- Combines NER (spaCy) + regex + custom recognizers
- 12+ built-in recognizers (email, phone, credit card, etc.)
- Extensible for PT-BR (CPF, CNPJ, RG, CEP, phone_br)
- **12/12 PT-BR patterns tested**

## Test Results
```
=== presidio PT-BR === 12/12 ✓
- email, CPF, CNPJ, RG, phone_br (9-digit), CEP
- bearer, sk_key, IPv4, credit card, Bearer JWT, mixed PT-BR
```

## Consequences
**Positive:**
- Catches PII regex would miss (e.g., "Meu CPF termina em 09")
- Easy to add new patterns
- Battle-tested

**Negative:**
- Adds 200MB dependency (spaCy model)
- Slower than pure regex (1ms vs 0.1ms per message)
