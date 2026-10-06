from _browser_runtime import get_manager
def run(inputs):
    sid = inputs.get("session_id")
    if not sid:
        tenant = inputs.get("tenant", "default")
        profile = inputs.get("profile")
        if not profile: return {"ok": False, "error": "session_id or profile required"}
        sid = f"{tenant}::{profile}"
    mgr = get_manager()
    ok = mgr.close(sid)
    if not ok: return {"ok": False, "error": f"session {sid} not found"}
    return {"ok": True, "closed": sid, "profile_persisted": True}
