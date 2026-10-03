"""Generate image from text (T2I)."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Generate image from text prompt.

    inputs:
        prompt (str): required, text description
        model (str): model endpoint ID (default: "nano-banana")
        aspect_ratio (str): "1:1", "16:9", "9:16", "4:3", "3:4", etc.
        resolution (str): "1K", "2K", "4K" or model-specific
        quality (str): "auto", "low", "medium", "high"
        seed (int): -1 for random
        negative_prompt (str): what to avoid
        steps (int): diffusion steps
        guidance_scale (float): CFG scale
        wait (bool): if True (default), poll until ready
        poll_timeout (int): max polling seconds

    returns:
        {"ok": True, "url": "...", "request_id": "..."}
        or {"ok": False, "error": "..."}
    """
    prompt = inputs.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    model = inputs.get("model") or "nano-banana"
    payload = {"prompt": prompt}

    if inputs.get("aspect_ratio"):
        payload["aspect_ratio"] = inputs["aspect_ratio"]
    if inputs.get("resolution"):
        payload["resolution"] = inputs["resolution"]
    if inputs.get("quality"):
        payload["quality"] = inputs["quality"]
    if inputs.get("seed") and int(inputs["seed"]) != -1:
        payload["seed"] = int(inputs["seed"])
    if inputs.get("negative_prompt"):
        payload["negative_prompt"] = inputs["negative_prompt"]
    if inputs.get("steps"):
        payload["steps"] = int(inputs["steps"])
    if inputs.get("guidance_scale"):
        payload["guidance_scale"] = float(inputs["guidance_scale"])

    # Submit
    result = request("POST", f"/api/v1/{model}", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        # Synchronous response (some endpoints)
        url = extract_output_url(submit)
        if url:
            return {"ok": True, "url": url, "request_id": None, "sync": True}
        return {"ok": False, "error": "no request_id and no output", "raw": submit}

    # Async — poll unless told not to
    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted",
                "poll_url": f"/api/v1/predictions/{request_id}/result"}

    # Poll (default 2s interval × 120 attempts = 4 min max)
    interval_ms = int(inputs.get("poll_interval_ms") or 2000)
    max_attempts = int(inputs.get("poll_max_attempts") or 120)
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