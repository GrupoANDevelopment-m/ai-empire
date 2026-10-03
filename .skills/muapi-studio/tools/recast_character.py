"""Recast character — swap face/character in a video with a reference image.

Mirrors RecastStudio (processRecast). Supports:
- kling-v3.0-pro-recast
- runway-act-two-recast
- wan2.2-animate-recast
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Recast a character in a video.

    inputs:
        video_url (str): required — source video to edit
        image_url (str): reference image of the character to insert
        model (str): one of "kling-v3.0-pro-recast", "runway-act-two-recast",
                     "wan2.2-animate-recast" (default: kling-v3.0-pro-recast)
        prompt (str): optional instructions
        aspect_ratio (str): output ratio
        character_orientation (str): how the character faces in the output
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    video_url = inputs.get("video_url")
    image_url = inputs.get("image_url")

    if not video_url:
        return {"ok": False, "error": "video_url required"}
    if not image_url:
        return {"ok": False, "error": "image_url required (reference character)"}

    model = inputs.get("model") or "kling-v3.0-pro-recast"
    payload = {
        "video_url": video_url,
        "image_url": image_url,
    }
    if inputs.get("prompt"):
        payload["prompt"] = inputs["prompt"]
    if inputs.get("aspect_ratio"):
        payload["aspect_ratio"] = inputs["aspect_ratio"]
    if inputs.get("character_orientation"):
        payload["character_orientation"] = inputs["character_orientation"]

    result = request("POST", f"/api/v1/{model}", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        return {"ok": True, "url": extract_output_url(submit), "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = poll_result(request_id,
                         int(inputs.get("poll_max_attempts") or 120),
                         int(inputs.get("poll_interval_ms") or 3000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "model": model,
    }