# ADR-0002: NVIDIA NIM as Default LLM Provider

## Status
Accepted — 2026-02-20

## Context
We need to pick a default LLM provider for AI Empire. Options:
1. **OpenAI** — industry standard, but requires credit card
2. **Anthropic Claude** — high quality, but requires credit card
3. **Ollama (local)** — free, but requires GPU on user's machine
4. **NVIDIA NIM** — free tier, no credit card, 100+ models
5. **Self-hosted (vLLM, TGI)** — full control, but operational burden

## Decision
**NVIDIA NIM is the new default.** Other providers remain configurable.

## Rationale
- **Free tier** — no credit card required to start
- **OpenAI-compatible API** — drop-in replacement, no code changes
- **100+ models** — Nemotron, Llama, Mistral, Phi, Gemma, Qwen
- **No GPU on user side** — runs on NVIDIA's infrastructure
- **Privacy option** — NIM is also self-hostable for enterprise

## Detection Order
1. Ollama (localhost:11434) — local dev
2. LiteLLM proxy — if user has one
3. **NVIDIA NIM** — default
4. OpenAI — if user has key
5. Anthropic — if user has key

## Consequences
**Positive:**
- Zero-friction onboarding
- Works on a free-tier developer machine
- No fake "demo" mode

**Negative:**
- Rate limits on free tier
- Dependence on NVIDIA uptime
- Some models still require credit card for higher rate limits
