"""delete_contact — real CRM contact deletion."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend


async def delete_contact(contact_id: str) -> dict:
    """
    Permanently delete a CRM contact.

    Args:
        contact_id: the CRM record ID

    Returns:
        {"ok": True, "deleted": str, "status": int}
    """
    if not contact_id:
        raise ValueError("contact_id is required")
    if backend() == "salesforce":
        r = await call("DELETE", f"/services/data/v60.0/sobjects/Contact/{contact_id}")
    else:
        r = await call("DELETE", f"/crm/v3/objects/contacts/{contact_id}")
    return {"ok": r.get("ok"), "deleted": contact_id, "status": r.get("status"),
            "error": None if r.get("ok") else (r.get("body") or r.get("error"))}
