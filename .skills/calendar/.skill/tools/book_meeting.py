"""book_meeting — real meeting booking (create event + invite)."""
import sys, os
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_d = os.path.dirname(os.path.abspath(__file__))
def _load(n):
    s = importlib.util.spec_from_file_location("bm_"+n, os.path.join(_d, n+".py"))
    m = importlib.util.module_from_spec(s); sys.modules["bm_"+n] = m
    s.loader.exec_module(m); return m


async def book_meeting(title: str, attendees: list, start: str = None,
                       duration_minutes: int = 30, description: str = "",
                       location: str = "", auto_pick_free: bool = True) -> dict:
    """
    Book a meeting: find a free slot if needed, then create the event and invite.

    Args:
        title: meeting title
        attendees: list of email addresses
        start: preferred ISO start (a free slot is picked if omitted)
        duration_minutes: length
        description: agenda / body
        location: physical or video location
        auto_pick_free: search for a free slot when start is not given

    Returns:
        {"ok": True, "event_id": str, "html_link": str, "start": str}
    """
    if not title.strip():
        raise ValueError("title is required")
    if not attendees:
        raise ValueError("at least one attendee email is required")
    for a in attendees:
        if "@" not in a:
            raise ValueError(f"invalid attendee email: {a}")

    ce = _load("create_event")
    if not start and auto_pick_free:
        fs = _load("find_slot")
        slots = await fs.find_slot(duration_minutes=duration_minutes, max_slots=1)
        if not slots.get("ok") or not slots.get("slots"):
            return {"ok": False, "error": "no free slot found in the next 14 days",
                    "error_detail": slots.get("error")}
        start = slots["slots"][0]["start"]

    r = await ce.create_event(title=title, start=start, duration_minutes=duration_minutes,
                              description=description, location=location,
                              attendees=attendees)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error"), "requested_start": start}
    return {"ok": True, "event_id": r["id"], "html_link": r.get("html_link"),
            "start": r["event"]["start"], "attendees": attendees,
            "backend": r.get("backend"), "duration_minutes": duration_minutes}
