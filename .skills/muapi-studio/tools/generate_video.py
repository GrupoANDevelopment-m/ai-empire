"""Generate video from text (T2V)."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Generate video from text prompt.

    inputs:
        prompt (str): required, what the video should show
        model (str): model endpoint ID (default: "kling-1.6-standard")
        aspect_ratio (str): "16:9", "9:16", "1:1"
        duration (int): seconds (5, 8, 10 depending on model)
        resolution (str): "480p", "720p", "1080p", "4K"
        quality (str): "standard", "pro", "high"
        mode (str): model-specific (e.g. "draft" for Seedance 2.5)
        seed (int): -1 for random
        wait (bool): default True — poll until done

    returns:
        {"ok": True, "url": "..."}
    """
    prompt = inputs.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    model = inputs.get("model") or "kling-1.6-standard"
    payload = {}

    if prompt:
        payload["prompt"] = prompt
    if inputs.get("aspect_ratio"):
        payload["aspect_ratio"] = inputs["aspect_ratio"]
    if inputs.get("duration"):
        payload["duration"] = int(inputs["duration"])
    if inputs.get("resolution"):
        payload["resolution"] = inputs["resolution"]
    if inputs.get("quality"):
        payload["quality"] = inputs["quality"]
    if inputs.get("mode"):
        payload["mode"] = inputs["mode"]
    if inputs.get("seed") and int(inputs["seed"]) != -1:
        payload["seed"] = int(inputs["seed"])

    result = request("POST", f"/api/v1/{model}", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        url = extract_output_url(submit)
        if url:
            return {"ok": True, "url": url, "sync": True}
        return {"ok": False, "error": "no request_id and no output", "raw": submit}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    # Videos take longer — default 5 min
    interval_ms = int(inputs.get("poll_interval_ms") or 3000)
    max_attempts = int(inputs.get("poll_max_attempts") or 100)
    polled = poll_result(request_id, max_attempts, interval_ms)

    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"],
                "attempts": polled.get("attempts")}

    url = extract_output_url(polled["data"])
    return {
        "ok": True,
        "request_id": request_id,
        "url": url,
        "attempts": polled.get("attempts"),
        "model": model,
        "prompt": prompt,
    }