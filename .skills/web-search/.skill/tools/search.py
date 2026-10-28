"""search — real web search (DuckDuckGo HTML + Bing fallback)."""
import sys, os, re, html as _h
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import fetch, UA


def _ddg_html(q, limit):
    return f"https://html.duckduckgo.com/html/?q={q.replace(' ', '+')}"


def _parse_ddg(body):
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        url, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if "uddg=" in url:
            from urllib.parse import urlparse, parse_qs, unquote
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [""])[0])
        out.append({"title": _h.unescape(title).strip(), "url": url})
    if not out:
        for m in re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.S):
            sn = _h.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            if sn:
                out.append({"snippet": sn[:300]})
    return out


def _parse_bing(body):
    out = []
    for m in re.finditer(r'<li class="b_algo".*?<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        out.append({"title": _h.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip(),
                    "url": m.group(1)})
    return out


async def search(query: str, limit: int = 10, engine: str = "duckduckgo") -> dict:
    """
    Search the web.

    Args:
        query: search terms
        limit: maximum results
        engine: "duckduckgo" | "bing"

    Returns:
        {"ok": True, "query": str, "engine": str, "results": [{"title","url","snippet"}]}
    """
    if not query or not query.strip():
        raise ValueError("query cannot be empty")
    from urllib.parse import quote_plus

    engines = {"duckduckgo": _ddg_html, "bing": lambda q, l: f"https://www.bing.com/search?q={quote_plus(q)}&count={l}"}
    if engine not in engines:
        raise ValueError(f"unsupported engine: {engine} (use duckduckgo or bing)")

    try:
        r = await fetch(engines[engine](query, limit), timeout=20)
        body = r["body"] if isinstance(r["body"], str) else str(r["body"])
        results = _parse_ddg(body) if engine == "duckduckgo" else _parse_bing(body)
        if not results and engine == "duckduckgo":
            r = await fetch(f"https://www.bing.com/search?q={quote_plus(query)}", timeout=20)
            results = _parse_bing(r["body"] if isinstance(r["body"], str) else str(r["body"]))
            engine = "bing (fallback)"
        # attach snippets
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', body, re.S) \
            if engine.startswith("duckduckgo") else []
        for i, res in enumerate(results[:limit]):
            if i < len(snippets):
                res["snippet"] = _h.unescape(re.sub(r"<[^>]+>", "", snippets[i])).strip()[:280]
            res.setdefault("url", "")
            res.setdefault("title", "untitled")
        return {"ok": True, "query": query, "engine": engine,
                "count": len(results[:limit]), "results": results[:limit]}
    except Exception as e:
        return {"ok": False, "query": query, "error": f"{type(e).__name__}: {str(e)[:160]}",
                "results": []}
