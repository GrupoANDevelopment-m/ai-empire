from _browser_runtime import run_action_sync
def run(inputs):
    sid, sel = inputs.get("session_id"), inputs.get("selector")
    if not sid or not sel: return {"ok": False, "error": "session_id and selector required"}
    return run_action_sync(sid, "fill", {"selector": sel, "value": inputs.get("value", "")})
