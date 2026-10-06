from _browser_runtime import run_action_sync
def run(inputs):
    sid = inputs.get("session_id")
    if not sid: return {"ok": False, "error": "session_id required"}
    p = {}
    if "selector" in inputs:
        p["selector"] = inputs["selector"]
        p["timeout_ms"] = inputs.get("timeout_ms", 10000)
    elif "ms" in inputs or "time_ms" in inputs:
        p["ms"] = inputs.get("ms") or inputs.get("time_ms")
    else: return {"ok": False, "error": "selector or ms required"}
    return run_action_sync(sid, "wait", p)
