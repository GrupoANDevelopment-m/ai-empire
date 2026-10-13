# Changelog

All notable changes to AI Empire will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - 2026-10-12

### Added
- **muapi-studio v4.0** — 40 tools, 121-model catalog from Vibe-Workflow + Open-Poe-AI + Design-Agent
- **browser-automation v1.0** — 13 real Playwright tools with persistent user sessions
- **NVIDIA NIM** as default LLM provider (free, OpenAI-compatible, no credit card)
- **Real library integration**:
  - tenacity (retry) — replaced 78 LOC of hand-rolled
  - pybreaker (circuit) — replaced 95 LOC of hand-rolled
  - presidio-analyzer + spaCy (PII) — replaced 9 LOC of regex
  - bleach 6.4.0 (XSS) — Mozilla production-grade
  - slowapi (rate limit) — Redis-backed, FastAPI-native
  - playwright 1.63.0 (browser) — real Chromium 1243
- **Channel adapters** with 2026-verified selectors (WhatsApp, Facebook, Discord, LinkedIn, Instagram, X)
- **forge.rollback()** — JSONL version history on disk
- **Sandbox** AST hardening — blocks subprocess, ctypes, pickle, fork
- **Helm chart** with multi-region, PDB, HPA, NetworkPolicy, ServiceMonitor
- **Database migrations** (Alembic) — 6 schemas: tenants, users, sessions, messages, skills, audit, data_files, knowledge, approvals
- **Grafana dashboards** — Overview, LLM Performance, Skills
- **Prometheus rules** — 9 alerts (error rate, latency, pod down, connections, memory, cost spike, OOM, PII leak, rate limit flood)
- **OTel collector** — traces → Tempo, metrics → Prometheus, logs → Loki
- **OpenAPI 3.0 spec** at docs/api/openapi.yaml
- **Architecture docs** — system overview, sequence diagrams, 5 ADRs
- **Runbooks** — high error rate, LLM cost spike
- **Tests** — 18 test files, ~1000 LOC: unit, integration, e2e, load
- **Client SDKs** — Python (async + sync), JavaScript/TypeScript, Go
- **Sample data** — conversations, workflows, datasets, prompts
- **MCP servers** — 8 implementations (stripe, github, filesystem, postgres, slack, google_maps, notion, hubspot)

### Changed
- **PII detection** from hand-rolled regex → Microsoft Presidio (12/12 PT-BR tested)
- **Resilience** from hand-rolled → tenacity + pybreaker
- **HTML sanitization** from manual → bleach

### Fixed
- forge.rollback() was NotImplementedError — now works
- 404 on missing files
- JWT secret < 32 bytes — now enforced
- Rate limit on login (5/min per IP)
- Cross-tenant access — now enforced
- Empty file/goal/recall — now rejected
- Fast-fail cognitive loop on empty inputs

### Security
- Multi-layer defense (Gate 0/1/2)
- Tenant isolation via ContextVar
- Append-only audit log with DB trigger
- PII auto-redaction (12 patterns)
- Image digest pinning
- OWASP ZAP pen-test in CI

### Performance
- 100+ req/s on /health (sequential)
- 120 req/s on /health (concurrent, 50 parallel)
- 101 req/s on /api/capabilities (with auth)

## [3.x] - 2026-08
- Earlier versions — see git history
