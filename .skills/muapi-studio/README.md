# muapi-studio skill

Wraps the MuAPI media generation API (api.muapi.ai) for use inside AI Empire.

This is an **integration**, not a rewrite. It uses the same OpenAPI endpoints
that [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI)
already exposes. If you have the UI app and want to use it standalone, that's
fine — this skill makes the same API callable from AI Empire's agent.

## What's wrapped (23 tools, 535+ models)

| Category | Tools | What it does |
|----------|-------|--------------|
| **Generation** | 9 tools | text/image/video → image/video/audio |
| **Video editing** | 4 tools | clipping, motion graphics, recast, character swap |
| **Motion** | 1 tool | motion transfer, object swap |
| **Image editing** | 4 tools | upscale, background removal, outpainting, layer decomposition |
| **Marketing** | 1 tool | brand-aligned ad generation |
| **Templates** | 2 tools | browse + execute community workflows/agents |
| **Account** | 2 tools | balance, history |

## Install

1. Get a MuAPI key at https://muapi.ai
2. Set `MUAPI_API_KEY` in your tenant config or `.env`
3. The skill ships with AI Empire as `.skills/muapi-studio/` — install via:
   ```bash
   ./empire skill install muapi-studio --from=.skills
   ```
4. Or via API:
   ```bash
   curl -X POST http://localhost:8123/api/capabilities/skills/muapi-studio/install-from-path?path=.skills/muapi-studio \
     -H "Authorization: Bearer $TOKEN"
   ```

## Usage from chat

The skill's capabilities are injected into the system prompt automatically when installed.
The agent can then call any of the 23 tools.

### Example prompts

```
"Make me a 16:9 thumbnail of a cyberpunk city at night, cinematic lighting."
→ [calls generate_image(...)]

"Animate this image (https://...) with the camera slowly zooming in."
→ [calls image_to_video(image_url=..., prompt="slow zoom in")]

"Extract 3 viral clips from this podcast video (https://...) in 9:16 for TikTok."
→ [calls clip_video(video_url=..., num_highlights=3, aspect_ratio="9:16")]

"Swap my face (https://...) into this dance video (https://...) preserving the motion."
→ [calls motion_control(video_url=..., image_url=..., mode="motion_transfer")]

"Upscale this 1024x1024 logo to 4K for print."
→ [calls upscale_image(image_url=..., model="seedvr2-image-upscale", resolution="4k")]

"What pre-built workflows exist for making Instagram Reels from product photos?"
→ [calls templates(kind="workflows", scope="template")]

"Check our remaining credits and burn down the history."
→ [calls account_balance() then generation_history(limit=20)]
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