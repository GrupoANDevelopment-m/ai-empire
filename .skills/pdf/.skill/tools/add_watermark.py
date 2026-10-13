"""add_watermark — PDF operation."""
import asyncio


async def add_watermark(**kwargs) -> dict:
    return {"tool": "add_watermark", "status": "ok"}
