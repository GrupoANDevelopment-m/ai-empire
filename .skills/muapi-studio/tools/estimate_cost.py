"""Estimate cost of a V2V generation before running.

Mirrors estimateV2VCost from muapi.js. Uses POST /api/v1/models/{endpoint}/estimate-cost
to predict credit cost without actually running the job.

Useful to:
- Avoid running expensive jobs without checking
- Compare cost across models
- Show price in UI before submission
"""
from _http import request


def run(inputs):
    """
    Estimate credit cost of a V2V generation.

    inputs:
        model (str): required — V2V model ID (e.g. "kling-v2v-master")
        video_url (str): required — input video
        prompt (str): optional
        strength (float): optional
        duration (int): optional — seconds
        aspect_ratio (str): optional

    returns:
        {"ok": True, "cost": N, "currency": "credits", "raw": {...}}
    """
    model = inputs.get("model")
    video_url = inputs.get("video_url")

    if not model:
        return {"ok": False, "error": "model required"}
    if not video_url:
        return {"ok": False, "error": "video_url required"}

    payload = {"video_url": video_url}
    if inputs.get("prompt"):
        payload["prompt"] = inputs["prompt"]
    if "strength" in inputs:
        payload["strength"] = float(inputs["strength"])
    if inputs.get("duration"):
        payload["duration"] = int(inputs["duration"])
    if inputs.get("aspect_ratio"):
        payload["aspect_ratio"] = inputs["aspect_ratio"]

    result = request("POST", f"/api/v1/models/{model}/estimate-cost",
                    body=payload, timeout=15)
    if not result["ok"]:
        return result

    data = result.get("data", {})
    cost = (data.get("cost") or
            data.get("credits") or
            data.get("amount") or
            data.get("price") or 0)
    return {
        "ok": True,
        "cost": cost,
        "model": model,
        "currency": "credits",
        "raw": data,
    }