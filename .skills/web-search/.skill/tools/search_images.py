"""search_images — real image search (Openverse API, no key required)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import fetch


async def search_images(query: str, limit: int = 10, license: str = None) -> dict:
    """
    Search freely-licensed images via the Openverse API.

    Args:
        query: search terms
        limit: max images
        license: filter — "commercial", "modification", or a code like "by", "cc0"

    Returns:
        {"ok": True, "results": [{"title","url","thumbnail","license","source"}]}
    """
    if not query.strip():
        raise ValueError("query cannot be empty")
    params = {"q": query, "page_size": min(limit, 20)}
    if license:
        params["license_type"] = "commercial" if license == "commercial" else license
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    try:
        r = await fetch(f"https://api.openverse.org/v1/images/?{qs}", timeout=25)
        data = r["body"]
        if not isinstance(data, dict):
            return {"ok": False, "error": "unexpected response shape"}
        out = [{
            "title": it.get("title", "")[:120],
            "url": it.get("url"),
            "thumbnail": it.get("thumbnail"),
            "license": it.get("license"),
            "license_version": it.get("license_version"),
            "creator": it.get("creator"),
            "source": it.get("source"),
            "width": it.get("width"), "height": it.get("height"),
        } for it in data.get("results", [])[:limit]]
        return {"ok": True, "query": query, "source": "Openverse",
                "count": len(out), "results": out}
    except Exception as e:
        return {"ok": False, "query": query, "error": f"{type(e).__name__}: {str(e)[:160]}",
                "results": []}
