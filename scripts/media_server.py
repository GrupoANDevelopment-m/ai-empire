"""
AI Empire Media Engine — HTTP server.

Exposes two endpoints with API compatibility:

  POST /prompt           — ComfyUI-compatible (port 8189)
    {prompt, aspect_ratio} → {image_path, image_url, tier, model, note}

  POST /generate         — Open-Sora-compatible (port 8200)
    {prompt, duration} → {video_path, video_url, tier, model, note}

If real GPU engines (ComfyUI / Open-Sora) are running, this server
proxies to them. Otherwise falls back to local CPU engines (T1 → T2).

Runs without GPU, without Docker, without external models in T2 mode.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("media-engine")

app = FastAPI(title="AI Empire Media Engine (CPU-first, GPU-accelerated)")

COMFYUI_URL = "http://localhost:8188"
OPENSORA_URL = "http://localhost:8200"


class ImgReq(BaseModel):
    prompt: str
    aspect_ratio: str = "1:1"


class VidReq(BaseModel):
    prompt: str
    duration: int = 5


@app.get("/")
def root():
    return {
        "name": "AI Empire Media Engine",
        "version": "2.4",
        "philosophy": "Colibrì-style multitier: T0 GPU > T1 CPU quantized > T2 procedural",
        "endpoints": ["/prompt (ComfyUI-compatible)", "/generate (Open-Sora-compatible)", "/health"],
        "tier_status": _tier_status(),
    }


@app.get("/health")
def health():
    return {"status": "ok", "tiers": _tier_status()}


def _tier_status() -> dict:
    """Check which tiers are available right now."""
    status = {"T0_GPU_ComfyUI": False, "T0_GPU_OpenSora": False,
              "T1_SD15_CPU": False, "T2_procedural": True}
    try:
        r = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=2)
        if r.status_code == 200:
            status["T0_GPU_ComfyUI"] = True
    except Exception:
        pass
    try:
        r = httpx.get(f"{OPENSORA_URL}/health", timeout=2)
        if r.status_code == 200:
            status["T0_GPU_OpenSora"] = True
    except Exception:
        pass
    if Path("/opt/empire/models/sd15").exists():
        status["T1_SD15_CPU"] = True
    return status


def _call_local_engine(mode: str, prompt: str, **kwargs) -> dict:
    """Use the local media_engine.py module directly."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import media_engine
    if mode == "image":
        return media_engine.generate_image(prompt, kwargs.get("aspect_ratio", "1:1"))
    else:
        return media_engine.generate_video(prompt, kwargs.get("duration", 5), "16:9")


@app.post("/prompt")
def prompt_endpoint(req: ImgReq):
    """ComfyUI-compatible — generate an image."""
    # Try T0 first
    try:
        r = httpx.post(COMFYUI_URL, json={"prompt": req.prompt}, timeout=30)
        if r.status_code == 200:
            return JSONResponse({"tier": "T0-ComfyUI", "model": "FLUX/SD on GPU",
                                "proxy": True, **(r.json())})
    except Exception:
        pass
    # Fall back to local engine
    return JSONResponse(_call_local_engine("image", req.prompt, aspect_ratio=req.aspect_ratio))


@app.post("/generate")
def generate_endpoint(req: VidReq):
    """Open-Sora-compatible — generate a video."""
    try:
        r = httpx.post(OPENSORA_URL, json={"prompt": req.prompt, "duration": req.duration}, timeout=30)
        if r.status_code == 200:
            return JSONResponse({"tier": "T0-OpenSora", "model": "Open-Sora on GPU",
                                "proxy": True, **(r.json())})
    except Exception:
        pass
    return JSONResponse(_call_local_engine("video", req.prompt, duration=req.duration))
