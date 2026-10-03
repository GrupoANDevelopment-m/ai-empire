# muapi-studio skill

Wraps the MuAPI media generation API (api.muapi.ai) for use inside AI Empire.

This is an **integration**, not a rewrite. It uses the same OpenAPI endpoints
that [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI)
already exposes. If you have the UI app and want to use it standalone, that's
fine — this skill makes the same API callable from AI Empire's agent.

## What's wrapped

| Mode | Description | Tools |
|------|-------------|-------|
| t2i  | Text → Image | `generate_image`, `list_models` |
| t2v  | Text → Video | `generate_video` |
| i2i  | Image → Image | `image_to_image` |
| i2v  | Image → Video | `image_to_video` |
| v2v  | Video → Video | `video_to_video` |
| audio | TTS, music, SFX | `generate_audio` |
| lipsync | Sync mouth to audio | `lip_sync` |

Plus utility:
- `upload_file` — get a public URL for a local file (MuAPI requires public URLs for inputs)

Total: 500+ models accessible.

## Install

1. Get a MuAPI key at https://muapi.ai
2. Set `MUAPI_API_KEY` in your tenant config or `.env`
3. The skill ships with AI Empire as `.skills/muapi-studio/` — install via:
   ```bash
   ./empire skill install muapi-studio --from=.skills
   ```

## Usage from chat

The skill's capabilities are injected into the system prompt automatically when installed.
The agent can then call any tool:

```
User:  "Make me a video of a cyberpunk city at night in 16:9, 10 seconds."
Agent: [calls generate_video(prompt="...", aspect_ratio="16:9", duration=10)]
       [polls until ready]
       [returns URL]
```

## Sandbox profile

Uses `heavy` profile because:
- Network access to `api.muapi.ai`
- Long timeout (default 5 min for video polling)
- More memory for processing results

Network policy in `skill.yaml` whitelists `*.muapi.ai` and blocks all metadata services.

## See also

- [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI) — the source UI
- `docs/MUAPI_INTEGRATION.md` — architecture and policy