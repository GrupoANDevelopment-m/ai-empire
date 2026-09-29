"""Render screenshot of capacidades page."""
import asyncio
from playwright.async_api import async_playwright

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
        await page.goto("file:///workspace/ai-empire/web/premium/capacidades.html",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        await page.screenshot(path="/workspace/ai-empire/web/premium/screenshot-capacidades-vp.png", full_page=False)
        await page.screenshot(path="/workspace/ai-empire/web/premium/screenshot-capacidades.png", full_page=True)
        await browser.close()
        print("done")

asyncio.run(shoot())
