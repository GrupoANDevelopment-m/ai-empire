# Changelog

All notable changes to AI Empire will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.1] - 2026-11-21

### Added
- `POST /api/tools/call` — executes a skill tool through the same dynamic
  registry the agent uses, inside the caller's tenant, with an audit entry.
- `POST /api/chat/stream` — one agent turn as Server-Sent Events, the REST
  counterpart of the `/ws/agent` WebSocket.
- `empire/worker.py` — publishes queued posts through the real platform
  APIs and retries with the actual error, bounded by `MAX_ATTEMPTS`.
- `empire/scheduler.py` — runs registered jobs on an interval or a
  five-field cron expression and records each run's real status and error.
- `scripts/backup.py` — real `pg_dump` and tar backups with pruning.
- `install_wheels.py` — a pip-free installer that resolves version ranges,
  propagates exact pins and caches wheels.
- `requirements-runtime.txt` — the resolved runtime dependency set.
- Verification harnesses: `tools_audit.py`, `tools_fake_success.py`,
  `tools_execute.py`, `tools_verify_single_exec.py`,
  `tools_verify_platform.py`, `tools_debug_react.py`.
- `benchmarks/run_load_test.py` — records a real load test with the
  environment and an explicit note that it is a local run.

### Fixed
- `execute_tool()` resolves the dynamic skill registry, so all 133
  advertised tools are executable (it previously knew 10).
- The tool discovery registry is cached by file mtime: it re-executed all
  133 modules on every call (0.495s → 0.0000s per lookup).
- An empty LLM completion is reported as an error instead of ending the
  turn with silence; an unusable payload now fails loudly.
- `httpx_compat` raises on transport failure instead of returning a
  status-0 response that callers could mistake for a real reply.
- `extract_key_points` falls back to TF-IDF when the LLM returns nothing
  usable, and labels which method produced the points.
- `web-search` falls back to Bing when DuckDuckGo fails at the transport
  level, not only when it returns an unparseable page.
- The `crm` skill manifest is valid YAML; an unquoted `*.salesforce.com`
  was parsed as an alias and the whole skill failed to load.
- 33 files no longer hardcode `/workspace/ai-empire`; the project root is
  resolved from each file's own location, so any checkout path works.
- `docker-compose.production.yml` parses: the `api-environment` and
  `api-volumes` anchors were referenced but never defined.
- The Helm chart renders: the secret template dereferenced a missing
  `.Values.jwt`, the grafana subchart collided with postgresql/redis over
  the bitnami/common library, and the pod anti-affinity labels were
  indented with `nindent 12` instead of 20.
- `pdf/add_watermark` attaches the page to the writer before merging, as
  pypdf 6.10+ requires.
- The Python SDK refreshes the Authorization header after login, reads the
  real `/api/capabilities` shape and sends a valid session value.
- The sanitizer removes script/style/iframe elements together with their
  content instead of leaving the script body as visible text.

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
