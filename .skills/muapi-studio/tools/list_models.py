"""List available models on MuAPI by mode (t2i, t2v, i2i, i2v, v2v, audio)."""
import json
from _http import request, request_public


def run(inputs):
    """
    List models by mode.

    inputs:
            mode (str):  one of "t2i", "t2v", "i2i", "i2v", "v2v", "audio", "all"
            limit (int):  max models to return (default: all)
            provider (str): filter by provider name (e.g. "Google", "OpenAI")
    returns:
            {"ok": True, "models": [...]} or
            {"ok": False, "error": "..."}
    """
    mode = (inputs.get("mode") or "t2i").lower()
    limit = inputs.get("limit")
    provider = inputs.get("provider")

    # The OpenAPI spec is a PUBLIC endpoint — fetching it must not require
    # an account key, and a failed fetch must be reported, never smoothed
    # over with an empty catalogue.
    result = request_public("GET", "/openapi.json", timeout=25)
    if not result.get("ok"):
        return {"ok": False, "mode": mode, "count": 0, "models": [],
                "error": result.get("error") or "could not fetch MuAPI OpenAPI spec",
                "source": "live"}

    models = []
    spec = result.get("data") or {}
    paths = spec.get("paths", {}) or {}
    # Collect all model endpoints
    for path, methods in paths.items():
        if not path.startswith("/api/v1/"):
            continue
        if "post" not in methods:
            continue
        endpoint = path[len("/api/v1/"):]
        post = methods["post"]
        summary = post.get("summary", "")
        tags = post.get("tags", [])
        if endpoint in ("predictions", "upload-binary", "get_upload_url",
                        "get_file_upload_url", "creative-agent"):
            continue
        models.append({
            "endpoint": endpoint,
            "summary": summary,
            "tags": tags,
        })

    # Apply filters. The live spec uses tags such as
    # "Image: Text-to-Image", "Video: Image-to-Video", "Image: Edit & Reference".
    if mode != "all":
        tag_mode_map = {
            "t2i": ["image: text-to-image"],
            "i2i": ["image: edit & reference", "image: enhance", "image: edit"],
            "t2v": ["video: text-to-video", "video: storyboard"],
            "i2v": ["video: image-to-video", "video: avatars"],
            "v2v": ["video: edit & effects"],
            "audio": ["audio", "lipsync", "lip-sync", "tts", "speech"],
            "3d": ["3d generation"],
            "agent": ["creative agent", "agent embeds", "zapier", "make"],
            "llm": ["llm / multimodal", "llm", "multimodal"],
        }
        target_tags = tag_mode_map.get(mode, [mode])
        filtered = []
        for m in models:
            haystack = " ".join(str(t).lower() for t in m.get("tags", []))
            if any(t in haystack for t in target_tags):
                filtered.append(m)
        models = filtered

    if provider:
        models = [m for m in models
                  if provider.lower() in m["summary"].lower()]

    if limit:
        models = models[:int(limit)]

    return {
        "ok": True,
        "mode": mode,
        "count": len(models),
        "models": models,
        "source": "live",
        "note": "fetched live from MuAPI OpenAPI spec — always current",
    }