"""add_activity — real CRM activity/note logging."""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend


async def add_activity(contact_id: str = None, deal_id: str = None,
                       activity_type: str = "note", body: str = "",
                       subject: str = "", due_date: str = None) -> dict:
    """
    Log an activity against a contact or deal.

    Args:
        contact_id: associate the activity with a contact
        deal_id: associate the activity with a deal
        activity_type: note | email | call | meeting | task
        body: activity notes
        subject: activity subject (email/meeting)
        due_date: ISO datetime for tasks/meetings

    Returns:
        {"ok": True, "id": str, "type": str}
    """
    if not (contact_id or deal_id):
        raise ValueError("contact_id or deal_id is required")
    if not body.strip() and not subject.strip():
        raise ValueError("body or subject is required")
    ts = due_date or datetime.now(timezone.utc).isoformat()

    if backend() == "salesforce":
        if activity_type == "email":
            obj, payload = "Task", {"Subject": subject or body[:60], "Description": body,
                                    "Status": "Completed", "ActivityDate": ts[:10],
                                    "WhoId": contact_id}
        elif activity_type in ("meeting", "call"):
            obj, payload = "Event", {"Subject": subject or activity_type,
                                     "Description": body, "StartDateTime": ts,
                                     "EndDateTime": ts, "WhoId": contact_id}
        else:
            obj, payload = "Task", {"Subject": subject or "Note", "Description": body,
                                    "Status": "Not Started", "ActivityDate": ts[:10],
                                    "WhoId": contact_id}
        r = await call("POST", f"/services/data/v60.0/sobjects/{obj}", body=payload)
    else:
        props = {"hs_timestamp": ts, "hs_note_body": body or subject,
                 "hs_activity_type": {"note": "NOTE", "email": "EMAIL",
                                      "call": "CALL", "meeting": "MEETING",
                                      "task": "TODO"}.get(activity_type, "NOTE"),
                 "hs_activity_subject": subject}
        if contact_id: props["associations__contacts"] = contact_id
        if deal_id: props["associations__deals"] = deal_id
        r = await call("POST", "/crm/v3/objects/notes", body={"properties": props})

    return {"ok": r.get("ok"), "id": (r.get("body") or {}).get("id"),
            "type": activity_type, "backend": backend(),
            "error": None if r.get("ok") else (r.get("body") or r.get("error"))}
