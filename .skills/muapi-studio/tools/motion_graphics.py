"""Motion graphics generation.

Mirrors VibeMotionStudio (runMotionGraphics / motion-graphics endpoint).
Used for short animated logos, intros, transitions — 6-second default.
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Generate motion graphics from a prompt.

    inputs:
        prompt (str): required — describe the motion graphic
        aspect_ratio (str): "16:9" (default), "9:16", "1:1", "4:3"
        duration_seconds (int): length (default: 6, max: ~15)
        wait (bool): default True

    returns:
        {"ok": True, "url": "...", "request_id": "..."}
    """
    prompt = inputs.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    payload = {
        "prompt": prompt,
        "aspect_ratio": inputs.get("aspect_ratio") or "16:9",
        "duration_seconds": int(inputs.get("duration_seconds") or 6),
    }

    result = request("POST", "/api/v1/motion-graphics", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        url = extract_output_url(submit)
        return {"ok": True, "url": url, "sync": True}

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
        "duration": payload["duration_seconds"],
    }