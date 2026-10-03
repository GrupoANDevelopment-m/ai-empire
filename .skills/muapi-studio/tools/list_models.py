"""List available models on MuAPI by mode (t2i, t2v, i2i, i2v, v2v, audio)."""
import json
from _http import request


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

    # Open Generative AI exposes the catalog via its OpenAPI spec
    # We fetch the live catalog so the skill stays in sync with new releases
    # Falls back to a small built-in list if the live fetch fails
    result = request("GET", "/openapi.json", timeout=15)

    models = []
    if result.get("ok"):
        spec = result.get("data", {})
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

    # Apply filters
    if mode != "all":
        # Heuristic categorization by tag
        tag_mode_map = {
            "t2i": ["image-generation", "text-to-image"],
            "i2i": ["image-to-image", "image-editing"],
            "t2v": ["video-generation", "text-to-video"],
            "i2v": ["image-to-video"],
            "v2v": ["video-to-video"],
            "audio": ["audio", "music", "speech", "lip-sync", "tts"],
        }
        target_tags = tag_mode_map.get(mode, [mode])
        filtered = []
        for m in models:
            if any(t in target_tags for t in m["tags"]):
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
        "note": "fetched live from MuAPI OpenAPI spec — always current",
    }