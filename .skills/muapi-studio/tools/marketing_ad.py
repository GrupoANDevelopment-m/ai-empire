"""Generate marketing ad videos with reference images/video.

Mirrors MarketingStudio (generateMarketingStudioAd).
Uses ByteDance Seedance 2 with reference inputs to produce brand-aligned ads.
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Generate a marketing ad video with reference assets.

    inputs:
        prompt (str): required — what the ad should show
        images_list (list): reference product images (default [])
        video_files (list): reference video clips (default [])
        aspect_ratio (str): "16:9" (default), "9:16", "1:1"
        resolution (str): "1080p" or default (uses premium variant)
        duration (int): seconds (default 5)
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    prompt = inputs.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    resolution = inputs.get("resolution") or ""
    endpoint = "sd-2-vip-omni-reference-1080p" if resolution == "1080p" else "seedance-2-vip-omni-reference"

    payload = {
        "prompt": prompt,
        "aspect_ratio": inputs.get("aspect_ratio") or "16:9",
        "duration": int(inputs.get("duration") or 5),
        "images_list": inputs.get("images_list") or [],
        "video_files": inputs.get("video_files") or [],
    }

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
                         int(inputs.get("poll_max_attempts") or 150),
                         int(inputs.get("poll_interval_ms") or 3000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "resolution": resolution or "default",
        "duration": payload["duration"],
    }