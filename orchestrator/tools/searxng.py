"""SearXNG wrapper — meta-busca local (privada)."""
from __future__ import annotations
import httpx
from config import settings


async def web_search(query: str, num_results: int = 10, engines: list[str] | None = None) -> list[dict]:
    """Busca no SearXNG. Retorna lista de {title, url, content, engine}."""
    params = {
        "q": query,
        "format": "json",
        "categories": "general",
        "engines": ",".join(engines) if engines else "google,bing,duckduckgo,brave",
        "count": num_results,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{settings.searxng_url}/search", params=params)
            r.raise_for_status()
            data = r.json()
            return [
                {
                    "title": res.get("title", ""),
                    "url": res.get("url", ""),
                    "content": res.get("content", ""),
                    "engine": res.get("engine", ""),
                }
                for res in data.get("results", [])
            ]
    except Exception as e:
        return [{"error": str(e), "query": query}]
