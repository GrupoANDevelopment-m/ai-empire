# AI Empire

**Self-hosted AI agent platform with 13 skills, 200+ tools, multi-region deployment.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Kubernetes ready](https://img.shields.io/badge/k8s-ready-green.svg)](deploy/helm/ai-empire/)
[![Production tested](https://img.shields.io/badge/production-tested-brightgreen.svg)](benchmarks/data/production_load_test.json)

AI Empire is a complete, production-ready AI agent platform. Install with one
command, customize per tenant, and run anywhere — local Docker, Kubernetes,
or AWS multi-region.

## Features

### 🧠 LLM-Agnostic
- **NVIDIA NIM** (default, free, no credit card)
- OpenAI, Anthropic, LiteLLM, Ollama
- Drop-in tool calling across all backends
- Streaming, JSON mode, vision

### 🛠️ 13 Skills, 200+ Tools

| Skill | Tools | Description |
|-------|-------|-------------|
| **browser-automation** | 13 | Real Chromium via Playwright — WhatsApp, LinkedIn, X, etc |
| **muapi-studio** | 40 | 121-model media generation (image, video, audio) |
| **saas-b2b** | 3 | Churn, ICP, MRR calculators |
| **email** | 10 | SMTP/IMAP with templates, bulk, attachments |
| **calendar** | 8 | Google/MS calendar, find slots, book meetings |
| **crm** | 10 | HubSpot/Salesforce, contacts, deals, pipeline |
| **social-media** | 10 | LinkedIn, X, Facebook, Instagram |
| **data-analysis** | 12 | pandas/numpy/scipy |
| **code-execution** | 6 | Python, JS, bash, SQL in sandbox |
| **web-search** | 8 | DuckDuckGo, Google, Bing + extraction |
| **pdf** | 10 | Create, parse, merge, encrypt PDFs |
| **translation** | 3 | 100+ languages |
| **summarization** | 4 | Extractive + abstractive |

### 🛡️ Production-Ready
- 3-gate security (auth → PII → sandbox)
- 12 PII patterns (CPF, CNPJ, RG, CEP, phone_br)
- Microsoft Presidio + bleach + slowapi
- Tenacity + pybreaker (replaced hand-rolled)
- Append-only audit log (DB trigger)
- Multi-tenant isolation
- Image digest pinning (SHA256)

### 📊 Observability
- OpenTelemetry traces/metrics/logs
- Prometheus + Grafana + Loki + Tempo
- 9 alert rules
- 3 Grafana dashboards (18 panels)
- Per-tenant metrics

### 🚀 Deployment
- Local: `./install.sh`
- Docker Compose: 16 services
- Kubernetes: Helm chart with HPA, PDB, NetworkPolicy
- Multi-region: Terraform (us-east-1, eu-west-1, ap-southeast-1)
- Auto-update via Watchtower

### 🧬 Resilience
- **Self-healing**: 6 strategies, auto-recovery
- **Self-learning**: feedback store, A/B tests, model ranker (UCB1)
- **Failover**: HealthMonitor + ServerPool with auto-promote
- **Circuit breaker**: pybreaker (battle-tested at Yelp/Mozilla)
- **Retry**: tenacity (battle-tested at SQLAlchemy/Requests)

## Quick Start

```bash
# Install
git clone https://github.com/GrupoANDevelopment-m/ai-empire
cd ai-empire
./install.sh

# Configure (NVIDIA NIM is default, free)
cp .env.example .env
# Edit .env with your NVIDIA_NIM_API_KEY (https://build.nvidia.com)

# Run
./empire chat
# Or web UI
./empire ui
# Open http://localhost:8080
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  AI Empire — System                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │   Web    │    │   CLI    │    │  Mobile  │              │
│  └─────┬────┘    └─────┬────┘    └─────┬────┘              │
│        └─────────────────┼─────────────────┘                │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────┐       │
│  │  FastAPI + WebSocket                            │       │
│  │  Gate 0: Auth + RBAC + Rate Limit               │       │
│  │  Gate 1: PII Redaction                          │       │
│  │  Gate 2: Sandbox + Audit                        │       │
│  └──────────────────────┬──────────────────────────┘       │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────┐       │
│  │  EmpireAgent (LangGraph state machine)          │       │
│  │  ├─ LLM Client (NVIDIA NIM / OpenAI / etc)     │       │
│  │  ├─ Skill Registry (13 skills)                  │       │
│  │  ├─ Memory (4 layers: STM/WTM/EM/SK)            │       │
│  │  ├─ Cognitive Loop (ACAMR)                      │       │
│  │  └─ HITL (Postgres approval queue)              │       │
│  └──────────────────────┬──────────────────────────┘       │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────┐       │
│  │  Resilience: Tenacity + PyBreaker               │       │
│  │  Self-Healing + Self-Learning + Failover        │       │
│  └──────────────────────┬──────────────────────────┘       │
│                          ▼                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  PostgreSQL  │  │    Redis     │  │ File Storage │     │
│  │  (with pgvec)│  │  (cache+rls) │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────┐       │
│  │  Observability: OTel → Prometheus/Loki/Tempo    │       │
│  │  → Grafana (3 dashboards, 18 panels)             │       │
│  └─────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Test Results

| Component | Status | Details |
|-----------|--------|---------|
| Server boot | ✓ | 1756 lines, all routes |
| Auth | ✓ | Real JWT, bcrypt, MFA support |
| LLM | ✓ | NVIDIA NIM end-to-end + tool calling |
| 200 tools | ✓ | 13 skills installed |
| Chromium 1243 | ✓ | Real Playwright 1.63 |
| PII PT-BR | ✓ | 12/12 patterns |
| Load test | ✓ | 200 concurrent at 120 RPS |
| Token leak | ✓ | 0 occurrences |

See [benchmarks/data/production_load_test.json](benchmarks/data/production_load_test.json) for full data.

## Documentation

- [Quickstart](docs/tutorials/01-quickstart.md)
- [Architecture](docs/architecture/system-overview.md)
- [ADRs](docs/architecture/decisions/)
- [Runbooks](docs/runbooks/)
- [API Reference](docs/api/openapi.yaml)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

MIT — see [LICENSE](LICENSE)
