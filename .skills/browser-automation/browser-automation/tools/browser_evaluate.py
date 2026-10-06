from _browser_runtime import run_action_sync
def run(inputs):
    sid = inputs.get("session_id")
    script = inputs.get("script") or inputs.get("js")
    if not sid or not script: return {"ok": False, "error": "session_id and script required"}
    return run_action_sync(sid, "evaluate", {"script": script})
