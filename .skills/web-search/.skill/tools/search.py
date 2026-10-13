"""search — search the web using DuckDuckGo (or configured engine)."""
import os
import asyncio
from typing import Optional
import httpx


async def search(query: str, limit: int = 10, engine: str = "duckduckgo") -> dict:
    """Search the web.

    Args:
        query: search query
        limit: max results
        engine: "duckduckgo" | "google" | "bing"
    """
    if engine == "duckduckgo":
        # Free, no API key needed
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            # Parse HTML results (in real impl, use BeautifulSoup)
            return {
                "engine": engine,
                "query": query,
                "results": [{"title": "Result", "url": "https://example.com"}] * min(limit, 5),
            }
    return {"engine": engine, "query": query, "results": []}
