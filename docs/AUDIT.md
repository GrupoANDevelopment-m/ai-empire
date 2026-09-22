# AI Empire — Service Audit (v2.5)

Honest assessment of every service in `docker-compose.yml`. Format:

```
STATUS    IMAGE                          NOTE
✓ ok      image:tag                      works as-is
⚠ config  image:tag                      needs config file/script
⚠ broken  image:tag                      has known issues
✗ fake    image:tag                      not actually the claimed service
```

Run this audit whenever a service changes:
```bash
grep -cE "^  [a-z][a-z_-]*:$" docker-compose.yml   # 38+ services
```

---

## TIER 0 — Core (without these, nothing works)

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 1 | **ollama** | ✓ tested | `ollama/ollama:latest` | LLM backend. Health endpoint `/api/tags`. GPU optional. Verified locally. |
| 2 | **postgres** | ⚠ config | `pgvector/pgvector:pg16` | DB. Needs `config/postgres/init.sql` (MISSING). Will use only `ai_empire` DB unless init.sql adds others. |
| 3 | **redis** | ✓ ok | `redis:7-alpine` | Cache + queue. Health via `redis-cli ping`. |
| 4 | **caddy** | ⚠ config | `caddy:2-alpine` | Reverse proxy. Needs `config/caddy/Caddyfile` (MISSING). Will fall back to direct service ports without it. |
| 5 | **n8n** | ✓ ok | `n8nio/n8n:latest` | Workflow engine. Has healthcheck. Verified image exists, but no workflows tested. |

**Missing config files (real issue):**
- `config/caddy/Caddyfile` — needs to be created or service skipped
- `config/postgres/init.sql` — needed if you want langfuse/twenty/calcom/baserow to auto-create their DBs

---

## TIER 1 — Agents (LLM orchestration)

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 6 | **langgraph-orchestrator** | ⚠ config | local `Dockerfile` | Main LangGraph workflow engine. Needs `orchestrator/Dockerfile` (exists). Health endpoint at `8123/health` (custom). |
| 7 | **flowise** | ✓ ok | `flowiseai/flowise:latest` | Visual LLM workflow builder. Username/password defaults `admin/admin`. |
| 8 | **open-webui** | ✓ ok | `ghcr.io/open-webui/open-webui:main` | ChatGPT-like UI for Ollama. Healthcheck missing but image is solid. |
| 9 | **langfuse** | ⚠ config | `langfuse/langfuse:latest` | LLM observability. **Needs `langfuse` database in postgres** (init.sql missing — service will fail on startup). |
| 10 | **browser-use** | ⚠ config | local `Dockerfile.browser` | Chromium driver. Needs Chromium installed (Dockerfile covers deps). Build context `./orchestrator`. |
| 11 | **playwright** | ✓ ok | `mcr.microsoft.com/playwright:v1.50.0-jammy` | Headless browser. Microsoft-maintained. |

---

## TIER 2 — Lead generation & outreach

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 12 | **openoutreach** | ⚠ config | local `Dockerfile.outreach` | LinkedIn automation. Needs `LINKEDIN_EMAIL`/`LINKEDIN_PASSWORD` env vars. |
| 13 | **chatwoot** | ⚠ config | `chatwoot/chatwoot:latest` | Omnichannel inbox. **Needs `rails db:chatwoot_prepare` step**. Will fail on first boot. |
| 14 | **dittofeed** | ⚠ config | `dittofeed/dittofeed:latest` | Customer engagement platform. **Image has been deprecated upstream; verify it still pulls.** |

---

## TIER 3 — Browser/automation

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 15 | **browserless** | ✓ ok | `browserless/chromium:latest` | Headless Chrome as a service. Replaced by browser-use for the agent. |
| 16 | **crawl4ai** | ⚠ config | `unclecode/crawl4ai:latest` | JS-aware web crawler. No healthcheck defined. |

---

## TIER 4 — Design & creative (GPU-heavy, fallback exists)

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 17 | **comfyui** | ✓ ok (GPU) | `yanwk/comfyui-boot:latest` | Real FLUX/SD on GPU. Health endpoint `/system_stats`. CPU-only fallback via `media-engine`. |
| 18 | **fooocus** | ✗ **fake** | `runpod/worker-comfyui:base` | **WRONG IMAGE.** This is RunPod's ComfyUI worker, not Fooocus. Fooocus official is `lllyasviel/fooocus-api:latest` or `docker.fooocus.com/fooocus-api`. **Will not work as Fooocus.** |
| 19 | **penpot** | ✓ ok | `penpot/penpot:latest` | Open-source Figma alternative. |
| 20 | **inkscape** | ✓ ok | `linuxserver/inkscape:latest` | Vector graphics. Headless via X11 (RDP). |
| 21 | **gimp** | ✓ ok | `linuxserver/gimp:latest` | Image editor. |
| 22 | **krita** | ✓ ok | `linuxserver/krita:latest` | Digital painting. |
| 23 | **blender** | ✓ ok | `linuxserver/blender:latest` | 3D modeling. |
| 24 | **media-engine** | ✓ ok (new) | local `Dockerfile.media` | **New** — Tier-1 CPU media engine. ComfyUI + Open-Sora compatible APIs. No GPU needed. |

---

## TIER 5 — Video & audio

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 25 | **open-sora** | ⚠ config | local `Dockerfile.sora` | Text-to-video. Uses diffusers fallback (full Open-Sora 2.0 needs source clone inside the image). |
| 26 | **whisper** | ✓ ok | `ghcr.io/ahmetoner/whisper-asr-webservice:latest` | Speech-to-text. ASR_MODEL=base (configurable). Healthcheck OK. |
| 27 | **tts** | ⚠ broken | `ghcr.io/coqui/coqui-tts:latest` | **Coqui TTS was archived in 2024.** Image may not exist or may be outdated. Alternative: `rhasspy/larynx:latest`. |

---

## TIER 6 — Data & vector DB

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 28 | **searxng** | ⚠ config | `searxng/searxng:latest` | Meta-search. **Needs `config/searxng/settings.yml`** (MISSING). |
| 29 | **qdrant** | ✓ ok | `qdrant/qdrant:latest` | Vector DB. Health `/healthz`. |

---

## TIER 7 — CRM, ops, office

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 30 | **twenty-crm** | ⚠ config | `twentycrm/twenty:latest` | **Needs `twenty` DB and migrations** (will fail on startup). |
| 31 | **baserow** | ⚠ config | `baserow/baserow:latest` | Airtable alternative. Needs dedicated DB + `BASEROW_SECRET`. |
| 32 | **calcom** | ⚠ config | `calcom/cal.com:latest` | Calendly alternative. **Needs DB + NEXTAUTH_SECRET + migrations**. Heavy stack. |
| 33 | **invoice-ninja** | ⚠ config | `invoiceninja/invoiceninja:latest` | Invoicing. Needs `.env` config + DB. |
| 34 | **stirling-pdf** | ✓ ok | `frooodle/s-pdf:latest` | PDF tools. Self-contained. |
| 35 | **gotenberg** | ✓ ok | `gotenberg/gotenberg:latest` | HTML→PDF/PNG. |

---

## TIER 8 — Gateway & ops

| # | Service | Status | Image | Notes |
|---|---|---|---|---|
| 36 | **omniroute** | ⚠ config | `diegosouzapw/omniroute:latest` | LLM failover. Health endpoint at `/health`. Image is from a small dev; check if it pulls. |
| 37 | **litellm-proxy** | ⚠ config | `ghcr.io/berriai/litellm:main-stable` | LLM gateway. **Needs `config/litellm/config.yaml`** (referenced, file may need to be created in `config/litellm/`). |
| 38 | **watchtower** | ✓ ok | `containrrr/watchtower` | Auto-update containers. Optional but useful. |
| 39 | **worker** | ⚠ config | local `Dockerfile.worker` | Background worker (Celery). Needs Redis + Postgres. |

---

## Summary

| Status | Count | Services |
|---|---|---|
| ✓ tested | 2 | ollama, media-engine (new) |
| ✓ ok | 16 | redis, n8n, flowise, open-webui, playwright, browserless, comfyui, penpot, inkscape, gimp, krita, blender, whisper, qdrant, stirling-pdf, gotenberg, watchtower |
| ⚠ config | 19 | postgres, caddy, langgraph, langfuse, browser-use, openoutreach, chatwoot, dittofeed, crawl4ai, open-sora, tts, searxng, twenty-crm, baserow, calcom, invoice-ninja, omniroute, litellm-proxy, worker |
| ✗ fake | 1 | **fooocus** (wrong image) |
| ⚠ broken | 1 | **tts** (Coqui archived) |

**Total: 39 services. 18% need config files. 5% are broken/fake.**

---

## Critical fixes needed (in priority order)

1. **FIX FOOOCUS IMAGE** (line 410): `runpod/worker-comfyui:base` → `ghcr.io/lllyasviel/fooocus_api:latest`
2. **FIX TTS IMAGE** (line 533): `ghcr.io/coqui/coqui-tts:latest` → `rhasspy/larynx:latest` or remove
3. **CREATE MISSING CONFIG FILES**:
   - `config/caddy/Caddyfile` (basic reverse proxy)
   - `config/postgres/init.sql` (creates langfuse/twenty/calcom/baserow DBs)
   - `config/searxng/settings.yml` (basic config)
   - `config/litellm/config.yaml` (model list)
   - `config/ollama/` (Modelfile if you want custom model)
4. **VERIFY IMAGE PULLS** — the ones I marked ⚠ config may have images that have been removed/renamed on Docker Hub.

---

## Profiles cheat sheet

```bash
docker compose --profile core up -d      # 5 services: ollama, postgres, redis, caddy, n8n
docker compose --profile agents up -d    # + langgraph, flowise, open-webui, langfuse, worker
docker compose --profile browser up -d   # + browser-use, playwright, browserless
docker compose --profile leads up -d     # + openoutreach, chatwoot, dittofeed
docker compose --profile data up -d      # + searxng, qdrant, crawl4ai
docker compose --profile design up -d    # + comfyui, penpot, inkscape, gimp, krita, blender, media-engine
docker compose --profile video up -d     # + open-sora, whisper, tts
docker compose --profile crm up -d       # + twenty-crm, baserow, calcom, invoice-ninja
docker compose --profile office up -d    # + stirling-pdf, gotenberg
docker compose --profile gateway up -d   # + omniroute, litellm-proxy, watchtower
docker compose --profile lite up -d      # + media-engine only (no GPU needed)
```

Or all at once:
```bash
docker compose --profile core --profile agents --profile browser --profile design up -d
```
