"""Expand image — outpainting / extend image canvas.

Mirrors LayersStudio (expandImage / ai-image-extension endpoint).
Extends the image beyond its original boundaries using AI.
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Expand an image beyond its current boundaries.

    inputs:
        image_url (str): required
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    image_url = inputs.get("image_url")
    if not image_url:
        return {"ok": False, "error": "image_url required"}

    payload = {"image_url": image_url}

    result = request("POST", "/api/v1/ai-image-extension",
                    body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        return {"ok": True, "url": extract_output_url(submit), "sync": True}

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
    }