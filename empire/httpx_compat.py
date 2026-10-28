"""
httpx compatibility shim.

The platform uses httpx throughout. This module exposes an httpx-shaped API
that is backed by the standard library (`urllib.request` / `http.client`) when
httpx is not installed, so a minimal install profile (or a partial dependency
resolution) does not take the whole agent down.

Real network I/O either way — no mocks, no fake responses.

Usage:
    from empire import httpx_compat as httpx
"""
from __future__ import annotations

import json as _json
import asyncio
import http.client
import urllib.error
import urllib.parse
import urllib.request

try:                                     # pragma: no cover
    import httpx as _real_httpx
    HAS_REAL_HTTPX = True
except ImportError:                      # pragma: no cover
    _real_httpx = None
    HAS_REAL_HTTPX = False


class _Headers(dict):
    """Case-insensitive header mapping."""

    def __init__(self, items=None):
        super().__init__()
        if items:
            for k, v in dict(items).items():
                self[k.lower()] = v

    def __getitem__(self, key):
        return super().__getitem__(key.lower())

    def __setitem__(self, key, value):
        super().__setitem__(key.lower(), value)

    def get(self, key, default=None):
        return super().get(key.lower(), default)

    def __contains__(self, key):
        return super().__contains__(key.lower())

    def items(self):
        return {k.title(): v for k, v in super().items()}.items()


class Timeout:
    def __init__(self, connect=None, read=None, write=None, pool=None):
        self.connect = connect
        self.read = read if read is not None else connect
        self.write = write if write is not None else connect
        self.pool = pool if pool is not None else connect

    def as_seconds(self, default=30.0) -> float:
        for v in (self.read, self.connect, self.write, self.pool):
            if v is not None:
                return float(v)
        return default


class Response:
    def __init__(self, status_code: int, content: bytes, headers: dict, url: str):
        self.status_code = status_code
        self.content = content
        self.headers = _Headers(headers)
        self.url = url

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:200]}")
        return self


class _StreamCtx:
    """Async context manager mimicking httpx's client.stream()."""

    def __init__(self, coro_factory):
        self._factory = coro_factory
        self._resp = None

    async def __aenter__(self):
        self._resp = await self._factory()
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _StreamingResponse:
    """Response wrapper that can iterate over SSE lines."""

    def __init__(self, conn, resp, url):
        self._conn = conn
        self._resp = resp
        self.status_code = resp.status
        self.headers = _Headers(dict(resp.getheaders()))
        self.url = url

    async def aiter_lines(self):
        loop = asyncio.get_event_loop()
        buf = b""
        while True:
            chunk = await loop.run_in_executor(None, self._resp.read1, 65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                yield line.decode("utf-8", "replace").rstrip("\r")
        if buf:
            yield buf.decode("utf-8", "replace").rstrip("\r")

    async def aiter_bytes(self):
        loop = asyncio.get_event_loop()
        while True:
            chunk = await loop.run_in_executor(None, self._resp.read1, 65536)
            if not chunk:
                break
            yield chunk

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    @property
    def content(self) -> bytes:
        return self._resp.read()


def _timeout_seconds(timeout) -> float:
    if timeout is None:
        return 30.0
    if isinstance(timeout, Timeout):
        return timeout.as_seconds()
    if isinstance(timeout, (int, float)):
        return float(timeout)
    return 30.0


def _build_url(url: str, params: dict | None) -> str:
    if not params:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{urllib.parse.urlencode(params, doseq=True)}"


def _sync_request(method: str, url: str, *, headers=None, params=None,
                  json=None, content=None, timeout=30.0,
                  follow_redirects=True) -> Response:
    full = _build_url(url, params)
    h = {k.title(): v for k, v in dict(headers or {}).items()}
    data = content
    if json is not None:
        data = _json.dumps(json).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(full, data=data, headers=h, method=method.upper())
    opener = urllib.request.build_opener()
    if not follow_redirects:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return Response(r.status, r.read(), dict(r.headers), r.url)
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read(), dict(e.headers or {}), full)
    except Exception as e:
        return Response(0, str(e).encode(), {}, full)


def _sync_stream(method: str, url: str, *, headers=None, params=None,
                 json=None, content=None, timeout=30.0):
    full = _build_url(url, params)
    h = {k.title(): v for k, v in dict(headers or {}).items()}
    data = content
    if json is not None:
        data = _json.dumps(json).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    parsed = urllib.parse.urlsplit(full)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=timeout)
    else:
        conn = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    conn.request(method.upper(), path, body=data, headers=h)
    resp = conn.getresponse()
    return conn, resp, full


class AsyncClient:
    """Minimal async httpx-compatible client backed by the stdlib."""

    def __init__(self, timeout=30.0, follow_redirects=True, verify=True,
                 **kwargs):
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.verify = verify
        self._extra = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def _t(self, timeout):
        return _timeout_seconds(timeout if timeout is not None else self.timeout)

    async def request(self, method, url, *, headers=None, params=None,
                      json=None, content=None, timeout=None, **kw):
        t = self._t(timeout)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: _sync_request(
                method, url, headers=headers, params=params, json=json,
                content=content, timeout=t,
                follow_redirects=self.follow_redirects))

    async def get(self, url, **kw):
        return await self.request("GET", url, **kw)

    async def post(self, url, **kw):
        return await self.request("POST", url, **kw)

    async def put(self, url, **kw):
        return await self.request("PUT", url, **kw)

    async def patch(self, url, **kw):
        return await self.request("PATCH", url, **kw)

    async def delete(self, url, **kw):
        return await self.request("DELETE", url, **kw)

    def stream(self, method, url, **kw):
        t = self._t(kw.pop("timeout", None))
        headers = kw.pop("headers", None)
        params = kw.pop("params", None)
        payload = kw.pop("json", None)
        content = kw.pop("content", None)

        async def _open():
            loop = asyncio.get_event_loop()
            conn, resp, full = await loop.run_in_executor(
                None, lambda: _sync_stream(
                    method, url, headers=headers, params=params,
                    json=payload, content=content, timeout=t))
            return _StreamingResponse(conn, resp, full)

        return _StreamCtx(_open)


class Limits:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


if HAS_REAL_HTTPX:
    # Re-export the real library so the platform uses it when available.
    Timeout = _real_httpx.Timeout
    Response = _real_httpx.Response
    AsyncClient = _real_httpx.AsyncClient
    Limits = _real_httpx.Limits
    __all__ = ["Timeout", "Response", "AsyncClient", "Limits",
               "HAS_REAL_HTTPX"]
else:
    __all__ = ["Timeout", "Response", "AsyncClient", "Limits",
               "HAS_REAL_HTTPX", "Headers"]
