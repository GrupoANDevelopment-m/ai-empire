# MuAPI Media Generation Integration

AI Empire uses **Open Generative AI's** underlying MuAPI provider to expose
**500+ AI models** (image, video, audio, lip-sync, cinema) as agent tools.

## What this is (and what it isn't)

This is an **integration**, not a rewrite:

- The Open Generative AI project (Next.js + Electron) wraps the same MuAPI REST API
- AI Empire's `muapi-studio` skill makes those same API endpoints callable from our agent
- Both can coexist: users can use Open Generative AI's UI for interactive work, and AI Empire for autonomous agent workflows
- We do NOT import Open Generative AI's React components — we just consume the same backend API

If you have Open Generative AI running standalone at port 3001, that's fine. If
you don't, you can use AI Empire's skill directly without it.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  AI Empire Agent (LLM)                          │
│   Reads system prompt → sees tool list → calls tool             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│          muapi-studio skill (sandboxed Python tools)            │
│   • generate_image       • generate_video       • generate_audio│
│   • image_to_image       • image_to_video       • video_to_video│
│   • lip_sync             • upload_file          • list_models    │
└──────────────────────────┬──────────────────────────────────────┘
                           │  HTTP (urllib), no extra deps
                           │  Header: x-api-key: $MUAPI_API_KEY
                           ▼
                ┌──────────────────────┐
                │  api.muapi.ai        │
                │  Submit + poll       │
                │  /api/v1/{model}     │
                │  /predictions/{id}/  │
                └──────────────────────┘
```

## Models exposed

| Mode | Count | Examples |
|------|-------|----------|
| t2i (text → image) | 78 | nano-banana, flux-dev, seedream-3, recraft-v3 |
| t2v (text → video) | 105 | kling-1.6, seedance-2.5-pro, sora-2, veo-3 |
| i2i (image → image) | 76 | flux-dev-i2i, ideogram-edit, recraft-style |
| i2v (image → video) | 173 | kling-i2v, seedance-i2v, minimax-i2v |
| v2v (video → video) | 85 | kling-v2v, style transfer, restyle |
| audio (TTS/music) | 18 | eleven-labs-tts, suno-music, sfx |

**Total: 535 models** across 14 studios.

## Setup

1. Get a free API key at https://muapi.ai
2. Set `MUAPI_API_KEY` in your `.env`:
   ```
   MUAPI_API_KEY=muapi_sk_xxxxxxxx
   ```
3. The skill ships with AI Empire at `.skills/muapi-studio/` — install with:
   ```bash
   ./empire skill install muapi-studio --from=.skills/muapi-studio
   ```
4. Or via API:
   ```bash
   curl -X POST http://localhost:8123/api/capabilities/skills/muapi-studio/install-from-path?path=.skills/muapi-studio \
     -H "Authorization: Bearer $TOKEN"
   ```

## Usage from chat

Once installed, the LLM automatically sees these tools and can call them.

### Example prompts

```
"Make me a 16:9 thumbnail of a cyberpunk city at night, cinematic lighting."
→ [calls generate_image(prompt="...", aspect_ratio="16:9", quality="high")]

"Animate this image (https://...) with the camera slowly zooming in."
→ [calls image_to_video(image_url=..., prompt="slow zoom in")]

"Generate a 30-second music track, ambient electronic, 128 BPM."
→ [calls generate_audio(prompt="ambient electronic 128 BPM", duration=30)]
```

### Direct API call

```bash
curl -X POST http://localhost:8123/api/capabilities/skills/muapi-studio/tools/generate_image \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cute robot", "model": "nano-banana", "aspect_ratio": "1:1"}'
```

## Sandbox security

The skill runs in AI Empire's Python sandbox:

- **AST validation** before execution — blocks `os.system`, `subprocess`, `eval`, etc.
- **Profile `heavy`** — allows HTTP outbound to `*.muapi.ai`
- **Network policy** in `skill.yaml` whitelists `api.muapi.ai`, `*.muapi.ai`, `cdn.muapi.ai`; blocks metadata services
- **Resource limits** — 5 CPU sec, 2 GB RAM, 60 sec timeout per call
- **File access** — only inside `EMPIRE_WORKDIR` (sandbox tempdir)

## Why not embed the Open Generative AI components?

We considered importing the Open Generative AI React components into AI Empire's UI but decided against it:

1. **Different stack** — Next.js + React vs FastAPI + server-rendered HTML
2. **Different use case** — Open Generative AI is interactive (user-driven); AI Empire is autonomous (agent-driven)
3. **API-level integration** — both consume the same MuAPI endpoints, so they stay in sync automatically
4. **Maintainability** — don't couple two projects' release cycles

The right level to integrate is the API, not the UI.

## Polling behavior

Most MuAPI endpoints are async (return a `request_id`, you poll for the result). The tools handle this transparently:

- Default: poll every 2 sec, max 120 attempts (~4 min for image)
- Videos: poll every 3 sec, max 100 attempts (~5 min)
- Override with `poll_interval_ms` and `poll_max_attempts` inputs
- Pass `wait=false` to get the request_id immediately and poll manually

## Cost

MuAPI charges per generation. Each tool call deducts credits from your MuAPI account. See https://muapi.ai/pricing for current rates.

## See also

- `.skills/muapi-studio/` — the skill implementation
- `docs/PEN_TEST.md` — security model
- [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI) — the source UI project
- https://muapi.ai — provider documentation