"""Decompose image into layers.

Mirrors LayersStudio (decomposeLayers / bytedance-seedream-5.0-pro-layer).
Uses ByteDance Seedream 5.0 Pro to split an image into its constituent layers.
"""
from _http import request, poll_result


def run(inputs):
    """
    Decompose an image into separate layers.

    inputs:
        image_url (str): required
        prompt (str): optional instructions for the decomposition
        resolution (str): "auto" (default), "1K", "2K", "4K"
        output_format (str): "png" (default), "jpeg", "webp"
        wait (bool): default True

    returns:
        {"ok": True, "images": ["url1", "url2", ...], "count": N}
    """
    image_url = inputs.get("image_url")
    if not image_url:
        return {"ok": False, "error": "image_url required"}

    payload = {
        "image_url": image_url,
        "prompt": inputs.get("prompt") or "",
        "resolution": inputs.get("resolution") or "auto",
        "output_format": inputs.get("output_format") or "png",
    }

    result = request("POST", "/api/v1/bytedance-seedream-5.0-pro-layer",
                    body=payload, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    request_id = submit.get("request_id") or submit.get("id")

    if not request_id:
        images = (submit.get("images") or
                  submit.get("output", {}).get("images") or
                  submit.get("outputs") or
                  ([submit["url"]] if submit.get("url") else []))
        return {"ok": True, "images": images, "count": len(images), "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = poll_result(request_id,
                         int(inputs.get("poll_max_attempts") or 90),
                         int(inputs.get("poll_interval_ms") or 2000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    data = polled["data"]
    images = (data.get("images") or
              data.get("output", {}).get("images") or
              data.get("outputs") or
              ([data["url"]] if data.get("url") else []))

    return {
        "ok": True,
        "request_id": request_id,
        "images": images,
        "count": len(images),
    }