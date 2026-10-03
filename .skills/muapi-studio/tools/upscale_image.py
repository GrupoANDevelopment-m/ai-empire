"""Upscale image to higher resolution.

Mirrors LayersStudio (upscaleImage). Supports 3 models:
- topaz-image-upscale: industry standard (configurable factor)
- seedvr2-image-upscale: diffusion transformer, up to 8K
- ai-image-upscaler: fast 1-click automatic
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Upscale an image to higher resolution.

    inputs:
        image_url (str): required
        model (str): "topaz-image-upscale" (default), "seedvr2-image-upscale",
                     "ai-image-upscaler"
        resolution (str): for seedvr2 — "4k" (default), "2k", "8k"
        upscale_factor (int): for topaz — 2, 3, 4, 6 (default 2)
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    image_url = inputs.get("image_url")
    if not image_url:
        return {"ok": False, "error": "image_url required"}

    model = inputs.get("model") or "topaz-image-upscale"
    payload = {"image_url": image_url}

    endpoint = model
    if model == "seedvr2-image-upscale":
        payload["resolution"] = inputs.get("resolution") or "4k"
    elif model == "topaz-image-upscale":
        payload["upscale_factor"] = int(inputs.get("upscale_factor") or 2)
    elif model == "ai-image-upscaler":
        endpoint = "ai-image-upscale"

    result = request("POST", f"/api/v1/{endpoint}", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        return {"ok": True, "url": extract_output_url(submit), "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = poll_result(request_id,
                         int(inputs.get("poll_max_attempts") or 60),
                         int(inputs.get("poll_interval_ms") or 2000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "model": model,
    }