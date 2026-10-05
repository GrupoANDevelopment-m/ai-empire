"""Browser actions — real Playwright ops."""
import os, json, asyncio, time
from typing import Dict, Any, Optional, List

ACTION_TYPES = ["navigate", "click", "fill", "extract", "screenshot", "evaluate",
                "wait", "scroll", "hover", "press", "type_text", "cookies",
                "save_state", "load_state"]


def list_action_types() -> List[str]:
    return ACTION_TYPES


async def _ensure_page(mgr, session):
    if session.session_id in mgr._pages:
        return mgr._pages[session.session_id]
    pwm = mgr._ensure_playwright()
    if not hasattr(mgr, "_pw_handle") or mgr._pw_handle is None:
        mgr._pw_handle = await pwm().start()
    pw = mgr._pw_handle
    browser_type = pw.chromium if session.browser_type == "chromium" else pw.firefox
    context = await browser_type.launch_persistent_context(
        user_data_dir=session.profile_dir, headless=session.headless,
        args=["--no-sandbox", "--disable-dev-shm-usage",
              "--disable-blink-features=AutomationControlled"],
    )
    mgr._browsers[session.session_id] = context
    page = context.pages[0] if context.pages else await context.new_page()
    mgr._pages[session.session_id] = page
    session.page_count = len(context.pages)
    return page


async def execute_action(session_id, action, params=None, tenant=None):
    from empire.browser.session import get_manager
    mgr = get_manager()
    s = mgr.get(session_id)
    if not s: return {"error": f"session {session_id} not found"}
    if s.status == "closed": return {"error": f"session {session_id} is closed"}
    params = params or {}
    page = mgr._pages.get(session_id)

    try:
        if action == "navigate":
            url = params.get("url")
            if not url: return {"error": "url required"}
            if not url.startswith(("http://", "https://", "file://", "data:", "about:")):
                url = "https://" + url
            page = await _ensure_page(mgr, s)
            response = await page.goto(url, wait_until="domcontentloaded",
                                       timeout=params.get("timeout_ms", 30000))
            s.current_url = page.url
            return {"ok": True, "url": page.url,
                    "status": response.status if response else None,
                    "title": await page.title()}

        if action == "click":
            if not params.get("selector"): return {"error": "selector required"}
            await page.click(params["selector"], timeout=params.get("timeout_ms", 5000))
            return {"ok": True, "clicked": params["selector"]}

        if action == "fill":
            if not params.get("selector"): return {"error": "selector required"}
            await page.fill(params["selector"], params.get("value", ""),
                            timeout=params.get("timeout_ms", 5000))
            return {"ok": True, "filled": params["selector"]}

        if action == "type_text":
            await page.type(params["selector"], params.get("text", ""),
                            delay=params.get("delay_ms", 30))
            return {"ok": True}

        if action == "extract":
            if not params.get("selector"):
                return {"ok": True, "text": await page.inner_text("body"),
                        "url": page.url}
            if params.get("attribute"):
                return {"ok": True, "value": await page.get_attribute(
                    params["selector"], params["attribute"])}
            return {"ok": True,
                    "text": await page.inner_text(params["selector"]),
                    "html": await page.inner_html(params["selector"])}

        if action == "screenshot":
            full = params.get("full_page", True)
            if params.get("path"):
                await page.screenshot(path=params["path"], full_page=full)
                return {"ok": True, "path": params["path"]}
            img = await page.screenshot(full_page=full)
            return {"ok": True, "size_bytes": len(img),
                    "image_hex": img.hex()}

        if action == "evaluate":
            script = params.get("script") or params.get("js")
            if not script: return {"error": "script required"}
            return {"ok": True, "result": str(await page.evaluate(script))[:5000]}

        if action == "wait":
            if "selector" in params:
                await page.wait_for_selector(params["selector"],
                                             timeout=params.get("timeout_ms", 10000))
                return {"ok": True}
            ms = params.get("ms") or params.get("time_ms") or 1000
            await asyncio.sleep(ms / 1000.0)
            return {"ok": True, "slept_ms": ms}

        if action == "scroll":
            x, y = params.get("x", 0), params.get("y", 500)
            await page.evaluate(f"window.scrollBy({x}, {y})")
            return {"ok": True}

        if action == "hover":
            if not params.get("selector"): return {"error": "selector required"}
            await page.hover(params["selector"])
            return {"ok": True}

        if action == "press":
            if not params.get("key"): return {"error": "key required"}
            await page.keyboard.press(params["key"])
            return {"ok": True}

        if action == "cookies":
            cookies = await page.context.cookies()
            return {"ok": True, "cookies": cookies, "count": len(cookies)}

        if action == "save_state":
            path = params.get("path")
            if not path: return {"error": "path required"}
            state = await page.context.storage_state(path=path)
            return {"ok": True, "path": path,
                    "cookies": len(state.get("cookies", []))}

        if action == "load_state":
            path = params.get("path")
            if not path or not os.path.exists(path):
                return {"error": f"state file not found: {path}"}
            with open(path) as f: state = json.load(f)
            await page.context.add_cookies(state.get("cookies", []))
            return {"ok": True, "loaded": len(state.get("cookies", []))}

        return {"error": f"unknown action: {action}", "valid": ACTION_TYPES}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:300]}"}


def run_action_sync(session_id, action, params=None, tenant=None):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(execute_action(session_id, action, params, tenant))
        finally: loop.close()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:300]}"}
