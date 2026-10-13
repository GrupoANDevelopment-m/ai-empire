"""Browser sidecar server — manages persistent Playwright contexts."""
import os
import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import uvicorn

PROFILE_ROOT = Path(os.getenv("PROFILE_ROOT", "/app/profiles"))
app = FastAPI(title="AI Empire Browser Sidecar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global playwright state
_pw = None
_browsers: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pw
    _pw = await async_playwright().start()
    PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
    yield
    for browser in _browsers.values():
        await browser.close()
    await _pw.stop()


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(_browsers),
        "profile_root": str(PROFILE_ROOT),
    }


@app.post("/sessions")
async def create_session(tenant_id: str, profile: str = "default", headless: bool = True):
    session_id = f"{tenant_id}_{profile}_{os.urandom(4).hex()}"
    profile_path = PROFILE_ROOT / tenant_id / profile
    profile_path.mkdir(parents=True, exist_ok=True)
    
    browser = await _pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_path),
        headless=headless,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    _browsers[session_id] = browser
    return {"session_id": session_id, "profile_path": str(profile_path)}


@app.delete("/sessions/{session_id}")
async def close_session(session_id: str):
    if session_id not in _browsers:
        raise HTTPException(404, "Session not found")
    await _browsers[session_id].close()
    del _browsers[session_id]
    return {"closed": session_id}


@app.post("/sessions/{session_id}/action")
async def session_action(session_id: str, action: dict):
    if session_id not in _browsers:
        raise HTTPException(404, "Session not found")
    browser = _browsers[session_id]
    page = browser.pages[0] if browser.pages else await browser.new_page()
    
    act = action.get("type")
    if act == "navigate":
        await page.goto(action["url"], wait_until=action.get("wait_until", "load"))
        return {"url": page.url, "title": await page.title()}
    if act == "click":
        await page.click(action["selector"])
        return {"clicked": action["selector"]}
    if act == "fill":
        await page.fill(action["selector"], action["value"])
        return {"filled": action["selector"]}
    if act == "extract":
        elements = await page.query_selector_all(action["selector"])
        attr = action.get("attr", "text")
        results = []
        for el in elements:
            if attr == "text":
                results.append(await el.text_content())
            else:
                results.append(await el.get_attribute(attr))
        return {"results": results}
    if act == "evaluate":
        result = await page.evaluate(action["script"])
        return {"result": result}
    if act == "screenshot":
        path = action.get("path")
        img = await page.screenshot(path=path, full_page=action.get("full_page", False))
        return {"size": len(img), "path": path}
    raise HTTPException(400, f"Unknown action: {act}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
