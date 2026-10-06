from _browser_runtime import run_action_sync
def run(inputs):
    sid = inputs.get("session_id")
    if not sid: return {"ok": False, "error": "session_id required"}
    p = {"full_page": inputs.get("full_page", True)}
    if "path" in inputs: p["path"] = inputs["path"]
    return run_action_sync(sid, "screenshot", p)
