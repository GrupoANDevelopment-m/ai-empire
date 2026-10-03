"""Calculate dynamic cost for a MuAPI task.

Mirrors calculateDynamicCost from muapi.js. POST /api/v1/app/calculate_dynamic_cost
returns the predicted cost for any task type, not just V2V.

Useful for: pricing dashboards, budget guards, "show price before run" UX.
"""
from _http import request


def run(inputs):
    """
    Calculate dynamic cost for a task.

    inputs:
        task_name (str): required — task identifier (e.g. "image_generation",
                         "video_generation", "image_to_video", "lip_sync")
        payload (dict): task-specific parameters

    returns:
        {"ok": True, "cost": N, "currency": "credits", "breakdown": {...}}
    """
    task_name = inputs.get("task_name")
    if not task_name:
        return {"ok": False, "error": "task_name required"}

    if "payload" in inputs and isinstance(inputs["payload"], dict):
        payload = inputs["payload"]
    else:
        payload = {k: v for k, v in inputs.items() if k not in ("task_name",)}

    result = request("POST", "/api/v1/app/calculate_dynamic_cost",
                    body={"task_name": task_name, "payload": payload},
                    timeout=15)
    if not result["ok"]:
        return result

    data = result.get("data", {})
    cost = (data.get("cost") or
            data.get("credits") or
            data.get("amount") or 0)
    return {
        "ok": True,
        "task_name": task_name,
        "cost": cost,
        "currency": "credits",
        "breakdown": data,
    }