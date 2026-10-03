"""Generate audio: TTS, music, sound effects (audio mode)."""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Generate audio from text.

    inputs:
        prompt (str): required — text, lyrics, or description
        model (str): audio model endpoint ID (e.g. "eleven-labs-tts", "suno-music")
        voice (str): voice ID for TTS models
        duration (int): seconds (music models)
        sound (str): sound effect description
        style (str): music style ("pop", "rock", etc.)
        bgm (bool): background music
        thinking (bool): enhance the prompt first
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    prompt = inputs.get("prompt")
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    model = inputs.get("model") or "eleven-labs-tts"
    payload = {"prompt": prompt}

    if inputs.get("voice"):
        payload["voice"] = inputs["voice"]
    if inputs.get("duration"):
        payload["duration"] = int(inputs["duration"])
    if inputs.get("sound"):
        payload["sound"] = inputs["sound"]
    if inputs.get("style"):
        payload["style"] = inputs["style"]
    if "bgm" in inputs:
        payload["bgm"] = bool(inputs["bgm"])
    if "thinking" in inputs:
        payload["thinking"] = bool(inputs["thinking"])

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

    interval_ms = int(inputs.get("poll_interval_ms") or 2000)
    max_attempts = int(inputs.get("poll_max_attempts") or 60)
    polled = poll_result(request_id, max_attempts, interval_ms)

    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    url = extract_output_url(polled["data"])
    return {
        "ok": True,
        "request_id": request_id,
        "url": url,
        "model": model,
    }