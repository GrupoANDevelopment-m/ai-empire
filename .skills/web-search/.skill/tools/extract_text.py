"""extract_text — real readable-text extraction from a page."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import fetch, strip_html


async def extract_text(url: str, selector: str = None,
                       max_chars: int = 30000) -> dict:
    """
    Extract readable text from a web page.

    Args:
        url: page URL (SSRF-checked)
        selector: optional CSS selector to scope extraction
        max_chars: truncation limit

    Returns:
        {"ok": True, "title": str, "text": str, "words": int}
    """
    from _fetch import check_url
    check_url(url)
    r = await fetch(url, timeout=25)
    html = r["body"] if isinstance(r["body"], str) else str(r["body"])

    if selector:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            node = soup.select_one(selector)
            text = strip_html(str(node)) if node else ""
            title = soup.title.string.strip()[:200] if soup.title else ""
        except ImportError:
            raise RuntimeError("selector requires bs4. Run: pip install beautifulsoup4 lxml")
    else:
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        if m:
            title = strip_html(m.group(1))[:200]
        # Prefer main/article content when present
        for pat in (r"(?is)<article[^>]*>(.*?)</article>",
                    r'(?is)<main[^>]*>(.*?)</main>',
                    r'(?is)<body[^>]*>(.*?)</body>'):
            m2 = re.search(pat, html)
            if m2:
                html = m2.group(1)
                break
        text = strip_html(html)

    text = text[:max_chars]
    return {"ok": r["status"] < 400, "status": r["status"], "url": url,
            "title": title, "text": text, "words": len(text.split()),
            "chars": len(text)}
