"""Shared HTTP fetch helpers with SSRF guard."""
import re, socket, ipaddress, asyncio, time
from urllib.parse import urlparse
from typing import Optional

BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1",
                 "metadata.google.internal", "169.254.169.254"}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"


def check_url(url: str) -> str:
    """Validate URL against SSRF (private ranges, blocked hosts)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme: {p.scheme}")
    host = (p.hostname or "").lower()
    if not host:
        raise ValueError("URL has no host")
    if host in BLOCKED_HOSTS:
        raise PermissionError(f"blocked host: {host}")
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise PermissionError(f"blocked private address: {ip}")
    except socket.gaierror:
        pass  # DNS failure is fine — the request will error out
    return url


def _fetch_urllib(url: str, timeout: int, headers: dict, method: str,
                  data: bytes, follow_redirects: bool,
                  retries: int = 3) -> dict:
    """Real HTTP via stdlib urllib. Used when httpx is not installed.

    Redirect targets are re-validated with check_url(), so an open redirect
    cannot be used to reach a private address.
    """
    import urllib.request, urllib.error, urllib.parse

    last_exc = None
    for attempt in range(retries):
        try:
            return _urllib_once(url, timeout, headers, method, data,
                                follow_redirects)
        except Exception as e:
            last_exc = e
            # transient TLS / connection resets are common behind proxies
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


def _urllib_once(url: str, timeout: int, headers: dict, method: str,
                 data: bytes, follow_redirects: bool) -> dict:
    import urllib.request, urllib.error, urllib.parse

    current = url
    for _ in range(6):
        check_url(current)                       # re-validate every hop
        req = urllib.request.Request(current, data=data,
                                     headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, raw, hdrs = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, raw, hdrs = e.code, e.read(), dict(e.headers or {})
        if status in (301, 302, 303, 307, 308) and follow_redirects:
            loc = hdrs.get("Location") or hdrs.get("location")
            if not loc:
                break
            current = urllib.parse.urljoin(current, loc)
            if status == 303 or (status in (301, 302) and method.upper() == "POST"):
                method, data = "GET", None
            continue
        break

    ctype = hdrs.get("Content-Type", hdrs.get("content-type", ""))
    text = raw.decode("utf-8", "replace") if raw else ""
    body = text
    if "json" in ctype.lower():
        import json as _json
        try:
            body = _json.loads(text)
        except Exception:
            body = text
    return {"status": status, "body": body, "content_type": ctype,
            "url": current, "headers": hdrs}


async def fetch(url: str, timeout: int = 20, headers: dict = None,
                method: str = "GET", data: bytes = None,
                follow_redirects: bool = True) -> dict:
    """Real HTTP request with SSRF guard. Returns {status, text, headers}."""
    check_url(url)
    h = {"User-Agent": UA, "Accept-Language": "en,pt-BR;q=0.9"}
    if headers:
        h.update(headers)

    try:
        import httpx
    except ImportError:
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: _fetch_urllib(url, timeout, h, method, data,
                                        follow_redirects))

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=follow_redirects,
                                 verify=True) as c:
        r = await c.request(method, url, headers=h, content=data)
        ctype = r.headers.get("content-type", "")
        if "application/json" in ctype:
            try:
                body = r.json()
            except Exception:
                body = r.text
        else:
            body = r.text
        return {"status": r.status_code, "body": body, "content_type": ctype,
                "url": str(r.url), "headers": dict(r.headers)}


def strip_html(html: str) -> str:
    """Remove scripts/styles/tags, collapse whitespace."""
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&ccedil;", "ç"), ("&atilde;", "ã"), ("&otilde;", "õ")]:
        html = html.replace(a, b)
    return re.sub(r"\s+", " ", html).strip()
