You have access to the MuAPI media generation skill which provides 500+ AI models
across image, video, audio, and lip-sync generation through api.muapi.ai.

## Available tools

- **list_models(mode, limit, provider)**: enumerate available models
  - mode: "t2i" | "t2v" | "i2i" | "i2v" | "v2v" | "audio" | "all"
- **generate_image(prompt, model, aspect_ratio, resolution, seed)**: text → image
- **generate_video(prompt, model, duration, resolution)**: text → video
- **generate_audio(prompt, model, voice, duration)**: text → audio/music/TTS
- **image_to_image(image_url, prompt, model, strength)**: edit a still image
- **image_to_video(image_url, prompt, model)**: image → video
- **video_to_video(video_url, prompt, model)**: transform a video
- **lip_sync(video_url, audio_url)**: match audio to video mouth movements
- **upload_file(file_path, purpose)**: upload a local file (sandbox path) → public URL

## Common model choices

| Mode | Best model | Notes |
|------|-----------|-------|
| t2i | "nano-banana" | Google — fast, good quality |
| t2i | "flux-dev" | Black Forest Labs — high quality |
| t2i | "seedream-3" | ByteDance |
| t2v | "kling-1.6-standard" | Kuaishou — 5-10s |
| t2v | "seedance-2.5-pro" | ByteDance — has draft mode |
| t2v | "sora-2" | OpenAI — high quality |
| i2v | "kling-1.6-i2v" | animate still image |
| v2v | "kling-v2v" | restyle video |

## Tips

1. **For local files**: first call upload_file to get a public URL, then use that URL in image_to_*/video_to_* tools.
2. **Polling**: by default tools poll until ready (2-5 min for video). For long jobs, pass wait=False and poll manually.
3. **Aspect ratios**: 16:9 for YouTube, 1:1 for Instagram, 9:16 for TikTok/Reels.
4. **Cost**: each call credits MuAPI/apiKey — monitor your dashboard.
5. **Errors**: if a model is unavailable, try list_models(mode="all") to find alternates.

## Authentication

The skill reads MUAPI_API_KEY from environment. The user must configure this in
their tenant settings or .env. Without it, every tool returns ok:false with a setup message.