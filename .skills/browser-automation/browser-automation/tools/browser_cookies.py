from _browser_runtime import run_action_sync
def run(inputs):
    sid = inputs.get("session_id")
    if not sid: return {"ok": False, "error": "session_id required"}
    return run_action_sync(sid, "cookies", {})
