"""fetch_url — real HTTP fetch with content-type routing."""
import sys, os, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import fetch, strip_html


async def fetch_url(url: str, timeout: int = 25, max_chars: int = 50000) -> dict:
    """
    Fetch a URL and return readable content.

    Args:
        url: the URL (http/https, SSRF-checked)
        timeout: seconds
        max_chars: truncate text output

    Returns:
        {"ok": True, "status": int, "content_type": str, "text"/"json"/"bytes": ...}
    """
    try:
        r = await fetch(url, timeout=timeout)
    except PermissionError as e:
        return {"ok": False, "url": url, "error": f"SSRF blocked: {e}"}
    except Exception as e:
        return {"ok": False, "url": url, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    ctype = r["content_type"]
    out = {"ok": r["status"] < 400, "status": r["status"], "url": r["url"],
           "content_type": ctype}

    if "json" in ctype:
        out["json"] = r["body"]
        out["text"] = str(r["body"])[:max_chars]
    elif ctype.startswith("text/html"):
        html = r["body"] if isinstance(r["body"], str) else str(r["body"])
        title = ""
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if m:
            title = strip_html(m.group(1))[:200]
        out["title"] = title
        out["text"] = strip_html(html)[:max_chars]
        out["chars"] = len(out["text"])
    elif ctype.startswith(("image/", "audio/", "video/", "application/octet")):
        out["is_binary"] = True
        out["bytes"] = len(str(r["body"]))
    else:
        out["text"] = (r["body"] if isinstance(r["body"], str) else str(r["body"]))[:max_chars]
    return out
