"""Calendar backend — real Google Calendar / Microsoft Graph."""
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "empire").is_dir() and (p / ".skills").is_dir())
import os, sys, asyncio
sys.path.insert(0, f"{_ROOT}/.skills/_shared")
import importlib.util

# Project root resolved from this file's location, so the code works
# from any checkout path (not just /workspace/ai-empire).
_s = importlib.util.spec_from_file_location(
    "empire_api", f"{_ROOT}/.skills/_shared/api.py")
api = importlib.util.module_from_spec(_s); _s.loader.exec_module(api)

GAPI = "https://www.googleapis.com/calendar/v3"


def backend() -> str:
    return os.getenv("CALENDAR_PROVIDER", "google").lower()


def _auth():
    if backend() in ("microsoft", "ms", "graph", "outlook"):
        t = api.need("MS_GRAPH_TOKEN", provider="Microsoft Graph")["MS_GRAPH_TOKEN"]
        return "graph", t, "https://graph.microsoft.com/v1.0/me/calendar"
    t = api.need("GOOGLE_CALENDAR_TOKEN", provider="Google Calendar")["GOOGLE_CALENDAR_TOKEN"]
    return "google", t, f"{GAPI}/calendars/primary"


def _h(tok):
    return api.bearer(tok)


async def call(method, path="", body=None, params=None, suffix=None):
    kind, tok, base = _auth()
    url = base + (path or "")
    if suffix:
        url = f"{base}{suffix}"
    return await api.request(method, url, headers=_h(tok),
                             json_body=body, params=params)
