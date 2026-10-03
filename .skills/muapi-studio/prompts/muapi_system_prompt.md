You have access to the **MuAPI media generation skill** — 23 tools that wrap
the same API as [Open Generative AI](https://github.com/Anil-matcha/Open-Generative-AI),
giving you access to 500+ AI models for image, video, audio, and lip-sync
generation and editing through api.muapi.ai.

## Tool reference (23 tools)

### Generation (9 tools)
- **list_models(mode, limit, provider)**: enumerate available models
  - mode: `"t2i"` | `"t2v"` | `"i2i"` | `"i2v"` | `"v2v"` | `"audio"` | `"all"`
- **generate_image(prompt, model, aspect_ratio, resolution, seed)**: text → image
- **generate_video(prompt, model, duration, resolution, mode)**: text → video
- **generate_audio(prompt, model, voice, duration, style, sound)**: TTS / music / SFX
- **image_to_image(image_url, prompt, model, strength)**: edit a still image
- **image_to_video(image_url, prompt, model, duration)**: image → video
- **video_to_video(video_url, prompt, model, strength)**: transform a video
- **lip_sync(video_url, audio_url)**: match audio track to video mouth
- **upload_file(file_path, purpose)**: upload local file → public URL (required for i2i/i2v/v2v/lipsync)

### Video editing (4 tools)
- **clip_video(video_url, num_highlights, aspect_ratio)**: AI video clipping
  - Extracts the most viral moments from long videos — perfect for TikTok/Reels/Shorts
  - Returns URLs of clips or coordinates (timestamps)
- **motion_graphics(prompt, aspect_ratio, duration_seconds)**: animated logos, intros, transitions
- **motion_graphics_edit(request_id, edit_prompt)**: edit a previously-generated motion graphic
- **recast_character(video_url, image_url, model)**: swap character in a video
  - Models: kling-v3.0-pro-recast, runway-act-two-recast, wan2.2-animate-recast

### Motion transfer (1 tool)
- **motion_control(video_url, image_url, mode, duration)**:
  - `mode="motion_transfer"`: extract motion from video, apply to new characters
  - `mode="objects_swap"`: swap characters/products/clothes in a video
  - Can take multiple reference images (up to 30)

### Image editing (4 tools)
- **upscale_image(image_url, model, resolution, upscale_factor)**:
  - Models: topaz-image-upscale (factor 2-6), seedvr2-image-upscale (4k/8k), ai-image-upscaler
- **remove_background(image_url)**: transparent background
- **expand_image(image_url)**: outpaint — extend image canvas with AI
- **decompose_layers(image_url, prompt)**: split image into layers (Seedream 5.0 Pro)

### Marketing & templates (3 tools)
- **marketing_ad(prompt, images_list, video_files, resolution, duration)**: brand ad with reference assets
  - `resolution="1080p"` uses the premium variant
- **templates(kind, scope)**: browse community templates
  - `kind="workflows"` or `"agents"`
  - `scope="template"` (community) or `"published"` or `"user"`
  - With `workflow_id`: returns full schema + node definitions
- **execute_template(workflow_id, inputs)**: run a pre-built workflow

### Account (2 tools)
- **account_balance()**: check current MuAPI credit balance
- **generation_history(cursor, limit)**: browse past generations

## Common model choices

| Mode | Best model | Notes |
|------|-----------|-------|
| t2i | `nano-banana` | Google — fast, good quality |
| t2i | `flux-dev` | Black Forest Labs — high quality |
| t2i | `seedream-3` | ByteDance |
| t2v | `kling-1.6-standard` | Kuaishou — 5-10s |
| t2v | `seedance-2.5-pro` | ByteDance — has draft mode |
| t2v | `sora-2` | OpenAI — high quality |
| i2v | `kling-1.6-i2v` | animate still image |
| v2v | `kling-v2v` | restyle video |
| recast | `kling-v3.0-pro-recast` | best quality |
| motion | `seedance-2.5-motion-control` | motion transfer / object swap |
| upscale | `topaz-image-upscale` | industry standard |
| upscale | `seedvr2-image-upscale` | up to 8K via diffusion |

## Tips

1. **For local files**: first call `upload_file` to get a public URL, then use that URL in `image_to_*` / `video_to_*` tools.
2. **Polling**: by default tools poll until ready (2-5 min for video). For long jobs, pass `wait=False` and poll manually.
3. **Aspect ratios**: 16:9 for YouTube, 1:1 for Instagram, 9:16 for TikTok/Reels.
4. **Cost**: each call credits MuAPI/apiKey. Use `account_balance()` before expensive jobs.
5. **For long videos → short clips**: use `clip_video` to auto-find viral moments.
6. **For brand consistency**: use `marketing_ad` with `images_list` of product photos.
7. **Errors**: if a model is unavailable, try `list_models(mode="all")` to find alternates.

## Authentication

The skill reads `MUAPI_API_KEY` from environment. The user must configure this in
their tenant settings or `.env`. Without it, every tool returns `ok:false` with a setup message.

## Open Generative AI coexistence

This skill uses the same backend as the Open Generative AI project. If the user
also has the Open Generative AI UI running, both can use the same MuAPI key
and see the same generations in their history.