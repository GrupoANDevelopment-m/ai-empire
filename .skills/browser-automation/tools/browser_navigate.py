from _browser_runtime import run_action_sync
def run(inputs):
    sid, url = inputs.get("session_id"), inputs.get("url")
    if not sid or not url: return {"ok": False, "error": "session_id and url required"}
    return run_action_sync(sid, "navigate", {"url": url, "timeout_ms": inputs.get("timeout_ms")})
