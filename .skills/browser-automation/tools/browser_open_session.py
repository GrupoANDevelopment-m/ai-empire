from _browser_runtime import get_manager, run_action_sync
def run(inputs):
    tenant = inputs.get("tenant", "default")
    profile = inputs.get("profile", "default")
    mgr = get_manager()
    s = mgr.get_or_create(tenant=tenant, profile=profile,
                          headless=inputs.get("headless", True),
                          browser_type=inputs.get("browser_type", "chromium"))
    nav = run_action_sync(s.session_id, "navigate",
                          {"url": inputs.get("start_url", "about:blank")}, tenant)
    return {"ok": True, "session": s.__dict__, "navigation": nav}
