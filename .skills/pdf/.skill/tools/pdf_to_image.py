"""pdf_to_image — PDF operation."""
import asyncio


async def pdf_to_image(**kwargs) -> dict:
    return {"tool": "pdf_to_image", "status": "ok"}
