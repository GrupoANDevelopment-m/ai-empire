"""Render screenshots of all premium pages."""
from pathlib import Path

# Project root resolved from this file's location, so the code works
# from any checkout path (not just /workspace/ai-empire).
_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "empire").is_dir() and (p / ".skills").is_dir())
import asyncio
from playwright.async_api import async_playwright


PAGES = [
    ("index.html",        "screenshot-full.png",    "screenshot-hero.png",   3000),
    ("login.html",        "screenshot-login.png",   "screenshot-login-vp.png", 1500),
    ("logs.html",         "screenshot-logs.png",    "screenshot-logs-vp.png",  2000),
    ("approvals.html",    "screenshot-approvals.png","screenshot-approvals-vp.png", 2000),
    ("configuracoes.html","screenshot-config.png",  "screenshot-config-hero.png", 3000),
]

async def shoot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu",
            "--enable-webgl", "--use-gl=swiftshader",
        ])
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        await ctx.add_init_script("""
            localStorage.setItem('empire.token', 'demo-token');
            localStorage.setItem('empire.tenant', 'default');
            localStorage.setItem('empire.user', JSON.stringify({email: 'admin@empire.local', role: 'admin'}));
        """)
        page = await ctx.new_page()
        for html, full, hero, wait_ms in PAGES:
            print(f"shooting {html}...", flush=True)
            await page.goto(f"file://{_ROOT}/web/premium/{html}",
                            wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(wait_ms)
            await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            await page.screenshot(path=f"{_ROOT}/web/premium/{full}", full_page=True)
            await page.screenshot(path=f"{_ROOT}/web/premium/{hero}", full_page=False)
        await browser.close()
        print(f"✓ {len(PAGES)} pages", flush=True)

asyncio.run(shoot())
