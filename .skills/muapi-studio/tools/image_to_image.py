"""Image-to-image transformation (I2I) — edits, style transfer, in-painting."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Transform an image with a text prompt.

    inputs:
        image_url (str): required — URL of source image (must be public)
        prompt (str): what to change about the image
        model (str): I2I model ID (default: "flux-dev-i2i")
        strength (float): 0.0-1.0 — how much to change (default: 0.6)
        aspect_ratio (str): output aspect ratio
        resolution (str): output resolution
        effect (str): special effect ID (model-specific)
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    image_url = inputs.get("image_url")
    prompt = inputs.get("prompt")

    if not image_url:
        return {"ok": False, "error": "image_url required"}

    model = inputs.get("model") or "flux-dev-i2i"
    payload = {"image_url": image_url}

    if prompt:
        payload["prompt"] = prompt
    if "strength" in inputs:
        payload["strength"] = float(inputs["strength"])
    if inputs.get("aspect_ratio"):
        payload["aspect_ratio"] = inputs["aspect_ratio"]
    if inputs.get("resolution"):
        payload["resolution"] = inputs["resolution"]
    if inputs.get("effect"):
        payload["effect"] = inputs["effect"]

    result = request("POST", f"/api/v1/{model}", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        url = extract_output_url(submit)
        if url:
            return {"ok": True, "url": url, "sync": True}
        return {"ok": False, "error": "no output", "raw": submit}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = poll_result(request_id,
                         int(inputs.get("poll_max_attempts") or 90),
                         int(inputs.get("poll_interval_ms") or 2000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "model": model,
    }