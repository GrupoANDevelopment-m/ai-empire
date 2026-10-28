"""update_event — real calendar event patch."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cal import call, backend


async def update_event(event_id: str, title: str = None, start: str = None,
                       end: str = None, description: str = None,
                       location: str = None) -> dict:
    """
    Update an existing calendar event (partial update).

    Args:
        event_id: the event identifier
        title: new title
        start: new ISO start
        end: new ISO end
        description: new body
        location: new location

    Returns:
        {"ok": True, "id": str, "updated": [...]}
    """
    if not event_id:
        raise ValueError("event_id is required")
    patch = {}
    if backend() == "google":
        if title: patch["summary"] = title
        if description: patch["description"] = description
        if location: patch["location"] = location
        if start: patch["start"] = {"dateTime": start, "timeZone": "UTC"}
        if end: patch["end"] = {"dateTime": end, "timeZone": "UTC"}
        if not patch:
            raise ValueError("nothing to update — pass at least one field")
        r = await call("PATCH", path=f"/{event_id}", body=patch)
    else:
        if title: patch["subject"] = title
        if description: patch["body"] = {"contentType": "HTML", "content": description}
        if location: patch["location"] = {"displayName": location}
        if start: patch["start"] = {"dateTime": start, "timeZone": "UTC"}
        if end: patch["end"] = {"dateTime": end, "timeZone": "UTC"}
        if not patch:
            raise ValueError("nothing to update — pass at least one field")
        r = await call("PATCH", suffix=f"/events/{event_id}", body=patch)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error")}
    return {"ok": True, "id": event_id, "updated": list(patch.keys()),
            "html_link": r["body"].get("htmlLink") or r["body"].get("webLink")}
