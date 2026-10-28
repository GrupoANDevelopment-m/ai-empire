from _browser_runtime import get_manager, run_action_sync


def run(inputs):
    """Open a persistent browser session for a tenant/profile.

    inputs:
        tenant (str): tenant id (default "default")
        profile (str): profile name — each profile keeps its own cookies
                       under data/browser_profiles/<tenant>/<profile>/
        headless (bool): run without a visible window (default True)
        browser_type (str): "chromium" or "firefox" (default chromium)
        start_url (str): page to open immediately (default "about:blank")

    returns:
        {"ok": True, "session": {...}, "navigation": {...}}
        or {"ok": False, "error": "..."} when the browser could not be started
    """
    tenant = inputs.get("tenant", "default")
    profile = inputs.get("profile", "default")
    mgr = get_manager()
    s = mgr.get_or_create(tenant=tenant, profile=profile,
                          headless=inputs.get("headless", True),
                          browser_type=inputs.get("browser_type", "chromium"))
    nav = run_action_sync(s.session_id, "navigate",
                          {"url": inputs.get("start_url", "about:blank")}, tenant)

    # The navigation result must be checked: a browser that failed to start
    # still produced a session record, and reporting ok=True would hide it.
    if isinstance(nav, dict) and not nav.get("ok"):
        return {"ok": False,
                "error": nav.get("error") or "browser navigation failed",
                "session": s.__dict__, "navigation": nav}
    return {"ok": True, "session": s.__dict__, "navigation": nav}
