from _browser_runtime import run_action_sync
def run(inputs):
    sid, path = inputs.get("session_id"), inputs.get("path")
    if not sid or not path: return {"ok": False, "error": "session_id and path required"}
    return run_action_sync(sid, "load_state", {"path": path})
