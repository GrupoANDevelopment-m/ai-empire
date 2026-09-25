# 🏰 AI Empire

<div align="center">

![CI](https://github.com/GrupoANDevelopment-m/ai-empire/workflows/CI/badge.svg)
![Security](https://img.shields.io/badge/security-OWASP%20Top%2010-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Services](https://img.shields.io/badge/services-38+-orange)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)

</div>


> Self-hosted AI agent platform. Real LLM with tool calling, 38+ Docker services, browser automation, lead sourcing, image/video gen. **One command installs everything.**

```bash
./install.sh   # installs Docker, Ollama, pulls models, starts 38+ services, runs 104 tests
./empire chat  # talk to the agent in your terminal
./empire ui    # open the web UI on http://localhost:7777
```

---

## ✨ What you get

A real LLM-backed agent — **not a pattern-matching bot**. The model picks which tool to call based on what you say.

### 8 native tools the LLM can call

| Tool | What it does | Real backend |
|---|---|---|
| `find_leads` | Discover B2B prospects | CrewAI/LangGraph + Playwright fallback |
| `send_outreach` | Draft cold email / WhatsApp / LinkedIn | n8n + LLM |
| `run_tests` | "run the circuit breaker tests" → pytest | 104 real tests |
| `health_check` | Are my services up? | HTTP probes |
| `generate_image` | Create images, banners, thumbnails | ComfyUI + FLUX.1-dev |
| `navigate_browser` | Drive a real Chromium browser | browser-use |
| `publish_social` | Post to Twitter / LinkedIn / etc. | n8n workflows |
| `watch_video` | Watch + summarize any video | yt-dlp + Whisper |

### 38+ Docker services

| Profile | Services |
|---|---|
| **core** | Ollama, PostgreSQL, Redis, n8n, MinIO |
| **agents** | LangGraph, CrewAI, browser-use, OpenOutreach |
| **gateway** | LiteLLM, OmniRoute, MCP gateway |
| **browser** | browser-use, crawl4ai, SearXNG |
| **leads** | OpenOutreach, PostgreSQL leads schema |
| **design** | ComfyUI, Fooocus, Penpot, Inkscape, GIMP, Krita, Blender |
| **video** | Open-Sora 2.0, Stable Video Diffusion, AnimateDiff |
| **data** | ClickHouse, Qdrant, Qdrant dashboard |
| **crm** | Chatwoot inbox |
| **office** | Penpot, OnlyOffice |

### Built-in resilience (no extra setup)

- **Circuit breaker** — auto-disable failing backends
- **Retry with exponential backoff + jitter** — never lose a request to a flake
- **Fallback chain** — primary → secondary → last-resort
- **Self-healing** — 6 strategies: RETRY, REPLAN, MODEL_SWITCH, TOOL_SUBSTITUTE, HUMAN_FALLBACK, GIVE_UP
- **Failover** — health monitor + server pool with auto-promote
- **Self-learning** — UCB1 multi-armed bandit ranks models per task type

---

## 🚀 Quick start

### Prerequisites
- macOS, Linux, or Windows (WSL2)
- Docker Desktop (https://www.docker.com/products/docker-desktop)
- ~20 GB free disk space (Ollama model + ComfyUI models)

### Install
```bash
unzip ai-empire.zip
cd ai-empire
./install.sh   # one command — installs deps, picks profiles, starts Docker, pulls Ollama model, runs 104 tests, launches chat
```

### Use
```bash
./empire chat   # CLI REPL — natural language
./empire ui     # Web UI on http://localhost:7777
./empire test   # Run the 104 real tests
```

### Example conversation
```
> find 10 leads from the Angola Ministry of Health
[TOOL CALL] find_leads({goal: "Angola Ministry of Health", limit: 10})
  → Dra. Sílvia Paula Valentim Lutucuta — Ministra da Saúde (minsa.gov.ao)
  → Dr. Carlos Alberto Pinto de Sousa — Secretário de Estado ... (minsa.gov.ao)
  → ... (10 real leads scraped via Playwright Chromium)

> create a 1:1 banner for the launch with "AI Empire is live"
[TOOL CALL] generate_image({prompt: "...", aspect_ratio: "1:1"})
  → PNG generated at /tmp/empire_generated/empire_xxx.png

> publish to twitter and linkedin
[TOOL CALL] publish_social({text: "...", channels: ["twitter", "linkedin"]})
  → Published ✓
```

---

## 🏗️ Architecture

```
                    ┌─────────────────────────────────────┐
                    │           Empire Agent (LLM)          │
                    │  ReAct loop · tool calling · memory  │
                    └─────────────────┬───────────────────┘
                                      │ HTTP
        ┌─────────────┬───────────────┼───────────────┬──────────────┐
        ▼             ▼               ▼               ▼              ▼
   CrewAI leads   browser-use     ComfyUI          n8n          run_tests
   + Playwright   Chromium       FLUX.1-dev      workflows     pytest
   + DDG-search                                                  104 tests
        │             │               │               │              │
        └─────────────┴───────────────┴───────────────┴──────────────┘
                                      │
                            Docker Compose (38+ services)
                                      │
                            Resilience layer
                  ┌───────────────────┼───────────────────┐
                  ▼                   ▼                   ▼
          Circuit Breaker      Self-Healing         Failover Pool
          (state machine)      (6 strategies)       (UCB1 ranker)
```

---

## 🧪 The 104 tests

Run them:
```bash
./empire test all
```

Breakdown:
- `circuit_breaker`: 18 tests
- `retry`: 8 tests
- `fallback`: 12 tests
- `self_healing`: 18 tests
- `learning`: 23 tests
- `failover`: 13 tests
- `e2e`: 6 tests
- `integration`: 4 (skipped without LiteLLM)
- `chaos`: 4 (skipped without Docker)

All real tests, not smoke tests.

---

## 🛠️ Configuration

Edit `.env` after install:

```bash
# LLM backend (auto-detected: Ollama > LiteLLM > OpenAI > Anthropic)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:0.5b

# Or use Claude / GPT directly
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional: lead enrichment
APIFY_API_KEY=...
CLEARBIT_API_KEY=...

# Optional: social publishing
TWITTER_BEARER_TOKEN=...
LINKEDIN_ACCESS_TOKEN=...
```

---

## 📁 Project structure

```
ai-empire/
├── bin/empire                  # CLI entry
├── install.sh                  # One-command installer
├── docker-compose.yml          # 38+ services, 10 profiles
├── web/
│   ├── server.py              # FastAPI + WebSocket
│   └── chat.html              # Streaming UI with tool viz
├── empire/
│   ├── agent/
│   │   ├── core.py            # Old (deprecated)
│   │   ├── llm_agent.py       # Singleton
│   │   └── llm/
│   │       ├── client.py      # Ollama / LiteLLM / OpenAI / Anthropic
│   │       ├── agent.py       # ReAct loop + streaming
│   │       └── tools.py       # 8 tool functions
│   └── nl/test_runner.py      # Natural language → pytest
├── orchestrator/              # LangGraph + CrewAI crews
│   ├── resilience/            # Circuit breaker, retry, fallback
│   ├── self_healing.py
│   ├── self_learning.py       # UCB1 model ranker
│   └── failover.py
├── assets/comfyui-workflows/  # 3 production workflows (IG, LinkedIn, YT)
├── scripts/
│   ├── real_leads.py          # Playwright fallback for find_leads
│   └── ...                    # install, start, stop, test, health-check
└── tests/                     # 104 pytest tests
```

---

## 🌍 Localization

Default: Portuguese (Angola-friendly) system prompt. The agent responds in the language you use.

---

## 📜 License

MIT — see LICENSE.

---

Built with: Ollama · LangGraph · CrewAI · browser-use · ComfyUI · FLUX.1-dev · Open-Sora 2.0 · Stable Video Diffusion · Playwright · LiteLLM · OmniRoute · OpenOutreach · SalesGPT · crawl4ai · n8n · Pytest · FastAPI · WebSocket
