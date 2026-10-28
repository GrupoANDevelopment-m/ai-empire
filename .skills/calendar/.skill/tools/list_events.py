"""list_events — real calendar event listing."""
import sys, os, asyncio
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cal import call, backend


async def list_events(days: int = 7, max_results: int = 50,
                      calendar_id: str = None) -> dict:
    """
    List upcoming calendar events.

    Args:
        days: how far ahead to look
        max_results: maximum events to return
        calendar_id: which calendar (default: primary)

    Returns:
        {"ok": True, "events": [{title,start,end,location,attendees}], "count": int}
    """
    now = datetime.now(timezone.utc)
    if backend() in ("google",):
        r = await call("GET", params={
            "timeMin": now.isoformat(),
            "timeMax": (now + timedelta(days=days)).isoformat(),
            "maxResults": max_results, "singleEvents": "true",
            "orderBy": "startTime"})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"),
                    "backend": "google"}
        evs = [{"title": e.get("summary", "(no title)"),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                "location": e.get("location"),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
                "html_link": e.get("htmlLink")} for e in r["body"].get("items", [])]
    else:
        r = await call("GET", suffix="/events", params={
            "$top": max_results,
            "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": (now + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "$orderby": "start/dateTime"})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"),
                    "backend": "graph"}
        evs = [{"title": e.get("subject", "(no title)"),
                "start": e.get("start", {}).get("dateTime"),
                "end": e.get("end", {}).get("dateTime"),
                "location": (e.get("location") or {}).get("displayName"),
                "attendees": [a.get("emailAddress", {}).get("address")
                              for a in e.get("attendees", [])],
                "html_link": e.get("webLink")} for e in r["body"].get("value", [])]
    return {"ok": True, "count": len(evs), "backend": backend(), "events": evs}
