"""AI video clipping — extract viral highlights from long videos.

Mirrors Open Generative AI's ClippingStudio (runClipping / ai-clipping endpoint).
Useful for TikTok/Reels/Shorts creators who want to auto-find the best moments.
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Extract highlights from a video using AI.

    inputs:
        video_url (str): required — public URL of source video
        num_highlights (int): how many clips to extract (default: 3, max: ~10)
        aspect_ratio (str): "9:16" (default, TikTok/Reels), "1:1", "16:9"
        return_coordinates_only (bool): if True, returns timestamps instead of clips

    returns:
        {"ok": True, "clips": [{"url": "...", "start": 0, "end": 15, "score": 0.95}]}
        or if return_coordinates_only=True:
        {"ok": True, "coordinates": [{"start": 0, "end": 15, "score": 0.95}]}
    """
    video_url = inputs.get("video_url")
    if not video_url:
        return {"ok": False, "error": "video_url required"}

    payload = {
        "video_url": video_url,
        "num_highlights": int(inputs.get("num_highlights") or 3),
        "aspect_ratio": inputs.get("aspect_ratio") or "9:16",
        "return_coordinates_only": bool(inputs.get("return_coordinates_only") or False),
    }

    result = request("POST", "/api/v1/ai-clipping", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        # Sync result
        return {
            "ok": True,
            "clips": submit.get("clips") or submit.get("outputs") or [],
            "sync": True,
        }

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = poll_result(request_id,
                         int(inputs.get("poll_max_attempts") or 60),
                         int(inputs.get("poll_interval_ms") or 2000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    data = polled["data"]
    if payload["return_coordinates_only"]:
        return {
            "ok": True,
            "request_id": request_id,
            "coordinates": data.get("coordinates") or data.get("outputs") or [],
        }

    return {
        "ok": True,
        "request_id": request_id,
        "clips": data.get("clips") or data.get("outputs") or [extract_output_url(data)],
    }