"""extract_images — PDF operation."""
import asyncio


async def extract_images(**kwargs) -> dict:
    return {"tool": "extract_images", "status": "ok"}
