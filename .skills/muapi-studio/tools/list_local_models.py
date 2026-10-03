"""List local AI models (sd.cpp + Wan2GP) from Open Generative AI's catalog.

Open Generative AI's desktop app supports running models locally:
- sd.cpp: bundled engine for image models (Z-Image Turbo, Dreamshaper, SDXL, etc)
- wan2gp: remote Gradio server for video models (Wan2.1, Wan2.2, Flux, Qwen)

This is useful for users who want to know which local models they can run
without using MuAPI credits.

Note: AI Empire doesn't ship the binaries — this just lists what's available
in the Open Generative AI local model catalog.
"""
# Local model catalog (from src/lib/localModels.js + electron/lib/modelCatalog.js)
# Snapshotted at integration time — Open Generative AI may add more models later
LOCAL_MODELS = {
    "sdcpp": [
        {"id": "z-image-turbo", "name": "Z-Image Turbo", "provider": "sdcpp",
         "type": "z-image", "size_gb": 3.4, "default_steps": 8,
         "description": "WaveSpeed's featured local model — 6B params, ultra-fast 8-step generation. No API key needed."},
        {"id": "z-image-base", "name": "Z-Image Base", "provider": "sdcpp",
         "type": "z-image", "size_gb": 3.5, "default_steps": 50,
         "description": "Full-quality 6B parameter model from Tongyi-MAI."},
        {"id": "dreamshaper-8", "name": "Dreamshaper 8", "provider": "sdcpp",
         "type": "sd1", "size_gb": 2.1, "default_steps": 20,
         "description": "Versatile SD 1.5 model — portraits, landscapes, artistic styles."},
        {"id": "realistic-vision-v51", "name": "Realistic Vision v5.1", "provider": "sdcpp",
         "type": "sd1", "size_gb": 2.0, "default_steps": 25,
         "description": "Photorealistic SD 1.5 — great for portraits and product shots."},
        {"id": "anything-v5", "name": "Anything V5", "provider": "sdcpp",
         "type": "sd1", "size_gb": 2.0, "default_steps": 25,
         "description": "Anime-style SD 1.5 — vibrant colors, clean linework."},
        {"id": "stable-diffusion-xl-base", "name": "SDXL Base", "provider": "sdcpp",
         "type": "sdxl", "size_gb": 6.9, "default_steps": 30,
         "description": "Official Stable Diffusion XL — higher resolution, excellent quality."},
    ],
    "wan2gp": [
        {"id": "wan2gp:flux-dev", "name": "Flux.1 Dev (Wan2GP)", "provider": "wan2gp",
         "type": "image", "family": "flux", "default_steps": 28,
         "description": "FLUX.1 dev served by Wan2GP. Requires running Wan2GP server."},
        {"id": "wan2gp:qwen-image", "name": "Qwen Image (Wan2GP)", "provider": "wan2gp",
         "type": "image", "family": "qwen",
         "description": "Qwen-Image text-to-image served by Wan2GP."},
        {"id": "wan2gp:wan22-t2v", "name": "Wan2.2 T2V (Wan2GP)", "provider": "wan2gp",
         "type": "video", "family": "wan",
         "description": "Wan2.2 text-to-video served by Wan2GP."},
        {"id": "wan2gp:wan22-i2v", "name": "Wan2.2 I2V (Wan2GP)", "provider": "wan2gp",
         "type": "video", "family": "wan",
         "description": "Wan2.2 image-to-video served by Wan2GP."},
    ],
}


def run(inputs):
    """
    List local AI models available in the Open Generative AI catalog.

    inputs:
        provider (str): "sdcpp", "wan2gp", or "all" (default: "all")
        type (str): filter by type — "image", "video", "z-image", "sd1", "sdxl"

    returns:
        {"ok": True, "models": [...], "count": N}
    """
    provider = (inputs.get("provider") or "all").lower()
    type_filter = inputs.get("type")

    items = []
    if provider in ("all", "sdcpp"):
        items.extend(LOCAL_MODELS["sdcpp"])
    if provider in ("all", "wan2gp"):
        items.extend(LOCAL_MODELS["wan2gp"])

    if type_filter:
        items = [m for m in items if m.get("type") == type_filter]

    return {
        "ok": True,
        "provider": provider,
        "type": type_filter,
        "models": items,
        "count": len(items),
        "note": "These models are from Open Generative AI's local catalog. AI Empire doesn't ship the binaries — install the Open Generative AI desktop app to use them offline.",
    }