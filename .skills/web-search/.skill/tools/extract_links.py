"""extract_links — real link extraction from a page."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import fetch
from urllib.parse import urljoin, urldefrag


async def extract_links(url: str, pattern: str = None,
                        same_domain: bool = False, limit: int = 200) -> dict:
    """
    Extract all links from a page.

    Args:
        url: page URL
        pattern: only keep links whose href matches this regex
        same_domain: restrict to the page's own host
        limit: maximum links returned

    Returns:
        {"ok": True, "count": int, "links": [{"text","href"}]}
    """
    from urllib.parse import urlparse
    r = await fetch(url, timeout=25)
    html = r["body"] if isinstance(r["body"], str) else str(r["body"])

    rx = re.compile(pattern) if pattern else None
    host = (urlparse(url).hostname or "").lower()
    links, seen = [], set()

    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href = m.group(1).strip()
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        full = urldefrag(urljoin(url, href))[0]
        if full in seen:
            continue
        if same_domain and (urlparse(full).hostname or "").lower() != host:
            continue
        if rx and not rx.search(full):
            continue
        seen.add(full)
        text = re.sub(r"<[^>]+>", " ", m.group(2))
        text = re.sub(r"\s+", " ", text).strip()[:150]
        links.append({"href": full, "text": text})
        if len(links) >= limit:
            break

    return {"ok": True, "url": url, "count": len(links), "links": links,
            "unique_domains": len({urlparse(l["href"]).hostname for l in links})}
