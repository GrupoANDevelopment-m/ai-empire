"""
Shared HTTP client for API-backed skills (calendar, crm, social-media).

Real HTTP calls. No mocks. Missing credentials raise a clear error naming
the exact env var to set — never a fake success response.
"""
import os, json, time, base64, asyncio
from typing import Any, Optional

try:
    import httpx
except ImportError:
    httpx = None

import urllib.request, urllib.error, urllib.parse


class MissingCredential(RuntimeError):
    pass


def need(*env_vars: str, provider: str = "") -> dict:
    """Return a mapping of env var -> value, raising if any is unset."""
    out, missing = {}, []
    for v in env_vars:
        val = os.getenv(v, "").strip()
        if not val:
            missing.append(v)
        else:
            out[v] = val
    if missing:
        raise MissingCredential(
            f"{provider or 'Provider'} not configured — set "
            + ", ".join(missing)
            + f" in .env. Create a key at https://{'developers.google.com' if 'GOOGLE' in missing[0] else 'app.hubspot.com' if 'HUBSPOT' in missing[0] else 'developers.facebook.com' if 'FACEBOOK' in missing[0] else 'linkedin.com/developers' if 'LINKEDIN' in missing[0] else 'dev.twitter.com' if 'TWITTER' in missing[0] else 'example.com'}"
        )
    return out


def _urllib_sync(method: str, url: str, headers: dict, json_body: Any,
                 params: dict, timeout: int, max_redirects: int = 5) -> dict:
    """Real HTTP via stdlib urllib (used when httpx is unavailable).

    Follows redirects manually (httpx normally does this) and re-sends the
    request against the new location, which is what SSRF revalidation in the
    web-search skill relies on.
    """
    if params:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urllib.parse.urlencode(params, doseq=True)}"

    current = url
    for _ in range(max_redirects + 1):
        data = None
        h = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(current, data=data, headers=h,
                                     method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                status, raw, hdrs = r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            status, raw, hdrs = e.code, e.read(), dict(e.headers or {})
            if status in (301, 302, 303, 307, 308):
                loc = hdrs.get("Location") or hdrs.get("location")
                if not loc:
                    break
                current = urllib.parse.urljoin(current, loc)
                if status == 303 or (status in (301, 302) and method.upper() == "POST"):
                    method, data, json_body = "GET", None, None
                continue
        except Exception:
            raise
        break

    ctype = hdrs.get("Content-Type", hdrs.get("content-type", ""))
    text = raw.decode("utf-8", "replace") if raw else ""
    body = None
    if "json" in ctype.lower():
        try:
            body = json.loads(text)
        except Exception:
            body = text
    elif raw:
        body = text
    return {"ok": status < 400, "status": status, "body": body,
            "headers": hdrs, "final_url": current}


async def request(method: str, url: str, *, headers: dict = None,
                  json_body: Any = None, params: dict = None,
                  timeout: int = 30, retries: int = 3) -> dict:
    """Real HTTP with retry/backoff on 429 and 5xx.

    Uses httpx when installed; otherwise falls back to the stdlib urllib
    transport. Both perform genuine network requests.
    """
    if httpx is None:
        last = None
        for attempt in range(retries):
            try:
                r = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _urllib_sync(method, url, headers or {},
                                               json_body, params, timeout))
                if r["status"] in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                return r
            except Exception as e:
                last = e
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return {"ok": False, "status": 0, "body": None,
                "error": f"{type(last).__name__}: {str(last)[:200]}"}

    last = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
                r = await c.request(method, url, headers=headers or {},
                                    json=json_body, params=params)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    ra = r.headers.get("retry-after")
                    await asyncio.sleep(float(ra) if ra else 2 ** attempt)
                    continue
                ctype = r.headers.get("content-type", "")
                body = r.json() if "json" in ctype else r.text
                return {"ok": r.status_code < 400, "status": r.status_code,
                        "body": body, "headers": dict(r.headers)}
        except Exception as e:
            last = e
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
    return {"ok": False, "status": 0, "body": None,
            "error": f"{type(last).__name__}: {str(last)[:200]}"}


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Accept": "application/json"}


def basic(user: str, pwd: str) -> dict:
    raw = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    return {"Authorization": f"Basic {raw}", "Accept": "application/json"}
