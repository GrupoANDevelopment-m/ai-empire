from _browser_runtime import get_manager
def run(inputs):
    mgr = get_manager()
    s = mgr.list_sessions(tenant=inputs.get("tenant"))
    return {"ok": True, "sessions": mgr.to_dicts(s), "count": len(s)}
