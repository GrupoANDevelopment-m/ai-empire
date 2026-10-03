"""Lip sync — match mouth movements to audio track."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Apply lip sync to a video using an audio track.

    inputs:
        video_url (str): required — source video URL
        audio_url (str): required — target audio track
        model (str): lip-sync model ID
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    video_url = inputs.get("video_url")
    audio_url = inputs.get("audio_url")

    if not video_url:
        return {"ok": False, "error": "video_url required"}
    if not audio_url:
        return {"ok": False, "error": "audio_url required"}

    model = inputs.get("model") or "sync-lipsync"
    payload = {
        "video_url": video_url,
        "audio_url": audio_url,
    }

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
                         int(inputs.get("poll_interval_ms") or 3000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": request_id,
        "url": extract_output_url(polled["data"]),
        "model": model,
    }