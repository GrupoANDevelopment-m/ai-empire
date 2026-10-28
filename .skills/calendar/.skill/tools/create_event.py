"""create_event — real calendar event creation."""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cal import call, backend


async def create_event(title: str, start: str, end: str = None,
                       duration_minutes: int = 60, description: str = "",
                       location: str = "", attendees: list = None,
                       timezone_name: str = "UTC") -> dict:
    """
    Create a calendar event.

    Args:
        title: event title
        start: ISO start datetime (e.g. "2026-10-25T14:00:00")
        end: ISO end datetime (computed from duration if omitted)
        duration_minutes: used when end is not given
        description: event body
        location: physical location
        attendees: list of emails to invite
        timezone_name: IANA timezone

    Returns:
        {"ok": True, "id": str, "html_link": str, "event": {...}}
    """
    if not title.strip():
        raise ValueError("title is required")
    if not start:
        raise ValueError("start is required")
    if not end:
        from datetime import timedelta
        s = datetime.fromisoformat(start)
        end = (s + timedelta(minutes=duration_minutes)).isoformat()

    if backend() == "google":
        body = {"summary": title, "description": description,
                "location": location, "start": {"dateTime": start, "timeZone": timezone_name},
                "end": {"dateTime": end, "timeZone": timezone_name}}
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        r = await call("POST", body=body)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "google"}
        return {"ok": True, "id": r["body"].get("id"),
                "html_link": r["body"].get("htmlLink"), "backend": "google",
                "event": {"title": r["body"].get("summary"),
                          "start": r["body"].get("start", {}).get("dateTime"),
                          "end": r["body"].get("end", {}).get("dateTime")}}

    body = {"subject": title, "body": {"contentType": "HTML", "content": description},
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
            "location": {"displayName": location} if location else None,
            "isOnlineMeeting": True}
    body = {k: v for k, v in body.items() if v is not None}
    if attendees:
        body["attendees"] = [{"emailAddress": {"address": a,
                             "type": "required"}} for a in attendees]
    r = await call("POST", suffix="/events", body=body)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "graph"}
    return {"ok": True, "id": r["body"].get("id"),
            "html_link": r["body"].get("webLink"), "backend": "graph",
            "event": {"title": r["body"].get("subject"),
                      "start": r["body"].get("start", {}).get("dateTime")}}
