# docker-compose.yml Audit Report

**Date:** 2026-09-19
**Auditor:** AI Empire Bot
**Scope:** 38 services, 24 volumes, 2 networks

---

## ✅ Fixed

| # | Issue | Fix |
|---|---|---|
| 1 | `${WHISPER_PORT:=9000}` invalid syntax (compose v2.20+ only) | Changed to `${WHISPER_PORT:-9000}` |
| 2 | `Dockerfile.outreach` re-installed `crewai crewai-tools` (duplicated, version conflict risk) | Removed duplicate, rely on requirements.txt |
| 3 | `Dockerfile.worker` re-installed `celery redis yt-dlp` (duplicated) | Removed redis/yt-dlp (in requirements), kept celery |
| 4 | 40 env vars referenced but missing from `.env.example` (`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `OLLAMA_HOST`, etc.) | Added all to `.env.example` |
| 5 | Missing healthchecks on critical services | Added 13 healthchecks (postgres, redis, ollama, n8n, langgraph, browser-use, comfyui, qdrant, searxng, openoutreach, whisper, tts, litellm) |
| 6 | Missing `depends_on: condition: service_healthy` (race conditions) | Added to 9 services that depend on postgres/redis/ollama |

---

## ⚠️ Known limitations (won't fix here)

| # | Issue | Why | Workaround |
|---|---|---|---|
| 1 | `open-sora` Dockerfile installs `diffusers transformers accelerate` — NOT real Open-Sora | Open-Sora needs source build + model weights download (~10GB). Image is pytorch:2.4.0-cuda12.1. | Use cloud GPU via RunPod, or wait for upstream stable image |
| 2 | `fooocus` uses `runpod/worker-comfyui:base` — generic image, not Fooocus | Real Fooocus image not on Docker Hub | Build custom or use ComfyUI workflow |
| 3 | `browser-use` Chrome installed via deprecated `apt-key add` | Cosmetic warning only, still works | Switch to signed-by in future |
| 4 | ComfyUI + Sora + Fooocus require GPU 12GB+ VRAM | Architectural — image gen needs GPU | Use cloud GPU (RunPod/Vast.ai) |
| 5 | No GPU in sandbox → those services can only be smoke-tested (`docker compose config`) | Sandbox limitation | Will work on user's Mac with Docker + (optional) GPU |
| 6 | `whisper-cpp` package name in requirements.txt may not exist on PyPI | Possible install failure | Pin `pywhispercpp` or specific version |
| 7 | `firecrawl-py` requires API key not in `.env.example` | Self-hosting vs cloud choice | Add `FIRECRAWL_API_KEY=` to `.env` if used |

---

## 🧪 Validation performed

1. ✓ YAML syntax valid (parsed with `yaml.safe_load`)
2. ✓ No port conflicts (38 services, 38 distinct host ports)
3. ✓ No undefined service dependencies (`depends_on` references all valid)
4. ✓ No undefined network references
5. ✓ No undefined named-volume references (all bind mounts point to existing paths)
6. ✓ All build contexts exist (`./orchestrator/Dockerfile*`)
7. ✓ All Dockerfiles have `EXPOSE` matching published ports
8. ✓ Main app (`orchestrator/main.py`) exposes `app = FastAPI(...)` at module level
9. ✓ All crew routes (`/crews/leads`, `/crews/design`, etc.) registered
10. ✓ Health endpoint `/health` returns `{"status":"ok",...}`

## 🧪 Validation NOT performed (can't, no Docker in sandbox)

- ✗ Real container build (`docker compose build`)
- ✗ Service startup (`docker compose up`)
- ✗ Inter-service connectivity
- ✗ GPU passthrough
- ✗ Volume permissions
- ✗ Network policies

---

## 📋 Pre-flight checklist for user

Before `./install.sh`, on a fresh Mac:

- [ ] Docker Desktop installed and running
- [ ] At least 16GB RAM (32GB+ for ComfyUI/Sora)
- [ ] 50GB free disk (or 500GB+ if running Sora/ComfyUI models)
- [ ] `cp .env.example .env` and edit passwords
- [ ] `./install.sh` (don't skip the system check step)

GPU is optional. Without GPU:
- ✓ All lead gen, scraping, browser, design workflows
- ✗ ComfyUI (image gen) — use cloud GPU
- ✗ Sora (video gen) — use cloud GPU
- ✗ FLUX/SDXL fast inference
