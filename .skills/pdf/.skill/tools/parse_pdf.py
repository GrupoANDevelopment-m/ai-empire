"""parse_pdf — PDF operation."""
import asyncio


async def parse_pdf(**kwargs) -> dict:
    return {"tool": "parse_pdf", "status": "ok"}
