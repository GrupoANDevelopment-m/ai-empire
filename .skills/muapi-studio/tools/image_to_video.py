"""Image-to-video (I2V) — animate a still image."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Animate a still image into a video.

    inputs:
        image_url (str): required — public URL of source image
        prompt (str): optional motion/action description
        model (str): I2V model ID (default: "kling-1.6-i2v")
        duration (int): seconds
        aspect_ratio (str): "16:9", "9:16", "1:1"
        resolution (str): "480p", "720p", "1080p"
        mode (str): model-specific mode
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    image_url = inputs.get("image_url")
    if not image_url:
        return {"ok": False, "error": "image_url required"}

    model = inputs.get("model") or "kling-1.6-i2v"
    payload = {"image_url": image_url}

    if inputs.get("prompt"):
        payload["prompt"] = inputs["prompt"]
    if inputs.get("duration"):
        payload["duration"] = int(inputs["duration"])
    if inputs.get("aspect_ratio"):
        payload["aspect_ratio"] = inputs["aspect_ratio"]
    if inputs.get("resolution"):
        payload["resolution"] = inputs["resolution"]
    if inputs.get("mode"):
        payload["mode"] = inputs["mode"]

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
                         int(inputs.get("poll_max_attempts") or 100),
                         int(inputs.get("poll_interval_ms") or 3000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "model": model,
    }