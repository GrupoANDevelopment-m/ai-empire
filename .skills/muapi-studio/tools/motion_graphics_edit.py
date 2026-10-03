"""Edit existing motion graphics with text instructions.

Mirrors VibeMotionStudio's edit flow (runMotionGraphicsEdit / motion-graphics-edit).
Useful for tweaking a previously-generated motion graphic without regenerating from scratch.
"""
from _http import request, poll_result, extract_output_url


def run(inputs):
    """
    Edit a motion graphic with a prompt.

    inputs:
        request_id (str): required — request_id from a previous motion_graphics call
        edit_prompt (str): required — what to change
        aspect_ratio (str): optional override
        duration_seconds (int): optional override
        wait (bool): default True

    returns:
        {"ok": True, "url": "..."}
    """
    request_id = inputs.get("request_id")
    edit_prompt = inputs.get("edit_prompt")

    if not request_id:
        return {"ok": False, "error": "request_id required (from previous motion_graphics call)"}
    if not edit_prompt:
        return {"ok": False, "error": "edit_prompt required"}

    payload = {
        "request_id": request_id,
        "edit_prompt": edit_prompt,
        "aspect_ratio": inputs.get("aspect_ratio") or "16:9",
        "duration_seconds": int(inputs.get("duration_seconds") or 6),
    }

    result = request("POST", "/api/v1/motion-graphics-edit", body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    new_request_id = submit.get("request_id") or submit.get("id")

    if not new_request_id:
        return {"ok": True, "url": extract_output_url(submit), "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": new_request_id, "status": "submitted"}

    polled = poll_result(new_request_id,
                         int(inputs.get("poll_max_attempts") or 60),
                         int(inputs.get("poll_interval_ms") or 2000))
    if not polled["ok"]:
        return {"ok": False, "request_id": new_request_id, "error": polled["error"]}

    return {
        "ok": True,
        "request_id": new_request_id,
        "url": extract_output_url(polled["data"]),
    }