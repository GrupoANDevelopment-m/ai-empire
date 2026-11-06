"""Take a screenshot of the AI Empire premium dashboard."""
from pathlib import Path

# Project root resolved from this file's location, so the code works
# from any checkout path (not just /workspace/ai-empire).
_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "empire").is_dir() and (p / ".skills").is_dir())
import asyncio
from playwright.async_api import async_playwright


async def take_screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--font-render-hinting=none",
        ])
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()
        await page.goto(f"file://{_ROOT}/web/premium/index.html",
                        wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Full-page screenshot
        await page.screenshot(
            path=f"{_ROOT}/web/premium/screenshot-full.png",
            full_page=True,
        )
        # Above-the-fold for hero preview
        await page.screenshot(
            path=f"{_ROOT}/web/premium/screenshot-hero.png",
            full_page=False,
        )
        await browser.close()
        print(f"✓ Full page: {_ROOT}/web/premium/screenshot-full.png")
        print(f"✓ Hero only: {_ROOT}/web/premium/screenshot-hero.png")

asyncio.run(take_screenshot())
