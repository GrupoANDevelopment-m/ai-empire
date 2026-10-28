"""delete_event — real calendar event deletion."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cal import call, backend


async def delete_event(event_id: str, send_notifications: bool = True) -> dict:
    """
    Delete a calendar event.

    Args:
        event_id: the event identifier
        send_notifications: email attendees about the cancellation

    Returns:
        {"ok": True, "deleted": str, "status": int}
    """
    if not event_id:
        raise ValueError("event_id is required")
    if backend() == "google":
        r = await call("DELETE", path=f"/{event_id}",
                       params={"sendUpdates": "all" if send_notifications else "none"})
    else:
        r = await call("DELETE", suffix=f"/events/{event_id}")
    return {"ok": r.get("ok"), "deleted": event_id, "status": r.get("status"),
            "error": None if r.get("ok") else (r.get("body") or r.get("error"))}
