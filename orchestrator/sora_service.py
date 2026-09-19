"""
Open-Sora service — text-to-video / image-to-video
Lightweight implementation using diffusers (for full Open-Sora 2.0,
clone https://github.com/hpcaitech/Open-Sora inside this image).
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

app = FastAPI(title="Open-Sora Service", version="1.0.0")


class T2VRequest(BaseModel):
    prompt: str
    duration: int = 4
    aspect_ratio: str = "16:9"
    fps: int = 24
    num_variants: int = 1


class I2VRequest(BaseModel):
    image_url: str
    duration: int = 4
    motion_strength: float = 0.6


@app.get("/health")
async def health():
    return {"status": "ok", "engine": "open-sora-2.0-fallback"}


@app.post("/generate")
async def generate(req: T2VRequest):
    """
    Generate video from text.
    Full version: clones https://github.com/hpcaitech/Open-Sora and runs
    scripts/diffusion/inference.py. This lightweight version returns a
    stub response with instructions.
    """
    return {
        "videos": [],
        "note": (
            "Open-Sora 2.0 inference requires the full source clone. "
            "Run inside this image: "
            "git clone https://github.com/hpcaitech/Open-Sora && cd Open-Sora && "
            "torchrun --nproc_per_node 1 --standalone scripts/diffusion/inference.py "
            "configs/diffusion/inference/256px.py --prompt 'your prompt'"
        ),
        "request": req.dict(),
    }


@app.post("/img2vid")
async def img2vid(req: I2VRequest):
    return {
        "videos": [],
        "note": "img2vid via SVD — use the design-video skill for full pipeline.",
        "request": req.dict(),
    }
