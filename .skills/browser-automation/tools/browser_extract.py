from _browser_runtime import run_action_sync
def run(inputs):
    sid = inputs.get("session_id")
    if not sid: return {"ok": False, "error": "session_id required"}
    p = {}
    if "selector" in inputs: p["selector"] = inputs["selector"]
    if "attribute" in inputs: p["attribute"] = inputs["attribute"]
    return run_action_sync(sid, "extract", p)
