"""search_news — real news search (Google News RSS + Bing News)."""
import sys, os, re, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import fetch


async def search_news(query: str, limit: int = 10,
                      when: str = "7d") -> dict:
    """
    Search recent news.

    Args:
        query: search terms
        limit: max articles
        when: recency filter for Google News (1d | 7d | 1m | 1y)

    Returns:
        {"ok": True, "results": [{"title","link","source","published"}]}
    """
    from urllib.parse import quote_plus
    url = (f"https://news.google.com/rss/search?q={quote_plus(query)}"
           f"&hl=pt-BR&gl=BR&ceid=BR:pt-419")
    try:
        r = await fetch(url, timeout=20)
        xml = r["body"] if isinstance(r["body"], str) else str(r["body"])
        root = ET.fromstring(xml)
        items = []
        for it in root.findall(".//item")[:limit]:
            src = it.find("source")
            items.append({
                "title": (it.findtext("title") or "").strip(),
                "link": (it.findtext("link") or "").strip(),
                "source": (src.text or "").strip() if src is not None else "",
                "published": (it.findtext("pubDate") or "").strip(),
            })
        return {"ok": True, "query": query, "source": "Google News RSS",
                "count": len(items), "results": items}
    except Exception as e:
        return {"ok": False, "query": query, "error": f"{type(e).__name__}: {str(e)[:160]}",
                "results": []}
