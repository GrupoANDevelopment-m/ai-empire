"""Video-to-video transformation (V2V) — restyle, edit, interpolate video."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Transform a video with a prompt.

    inputs:
        video_url (str): required — public URL of source video
        prompt (str): transformation to perform
        model (str): V2V model ID
        strength (float): 0.0-1.0 — how much to change
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    video_url = inputs.get("video_url")
    if not video_url:
        return {"ok": False, "error": "video_url required"}

    model = inputs.get("model") or "kling-v2v"
    payload = {"video_url": video_url}

    if inputs.get("prompt"):
        payload["prompt"] = inputs["prompt"]
    if "strength" in inputs:
        payload["strength"] = float(inputs["strength"])
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
                         int(inputs.get("poll_max_attempts") or 120),
                         int(inputs.get("poll_interval_ms") or 5000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "model": model,
    }