"""Render screenshots of the new dashboard + configuracoes page."""
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
        page = await ctx.new_page()

        # Dashboard — full page
        await page.goto("file:///workspace/ai-empire/web/premium/index.html",
                        wait_until="networkidle")
        await page.wait_for_timeout(3000)
        await page.screenshot(
            path="/workspace/ai-empire/web/premium/screenshot-full.png",
            full_page=True,
        )
        await page.screenshot(
            path="/workspace/ai-empire/web/premium/screenshot-hero.png",
            full_page=False,
        )

        # Config page — full
        await page.goto("file:///workspace/ai-empire/web/premium/configuracoes.html",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        # Force a render flush
        await page.evaluate("() => document.body.offsetHeight")
        await page.screenshot(
            path="/workspace/ai-empire/web/premium/screenshot-config.png",
            full_page=True,
        )
        await page.screenshot(
            path="/workspace/ai-empire/web/premium/screenshot-config-hero.png",
            full_page=False,
        )

        await browser.close()
        print("✓ dashboard full + hero")
        print("✓ config full + hero")

asyncio.run(shoot())
