"""update_contact — real CRM contact update."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend


async def update_contact(contact_id: str, first_name: str = None,
                         last_name: str = None, company: str = None,
                         phone: str = None, lifecycle_stage: str = None) -> dict:
    """
    Update a CRM contact.

    Args:
        contact_id: the CRM record ID
        first_name / last_name / company / phone / lifecycle_stage: fields to change

    Returns:
        {"ok": True, "id": str, "updated": [...]}
    """
    if not contact_id:
        raise ValueError("contact_id is required")
    if backend() == "salesforce":
        mapping = {"first_name": "FirstName", "last_name": "LastName",
                   "company": "Company", "phone": "Phone"}
        body = {mapping[k]: v for k, v in
                (("first_name", first_name), ("last_name", last_name),
                 ("company", company), ("phone", phone)) if v}
        if not body:
            raise ValueError("nothing to update")
        r = await call("PATCH", f"/services/data/v60.0/sobjects/Contact/{contact_id}", body=body)
        return {"ok": r.get("ok"), "id": contact_id, "updated": list(body.keys()),
                "error": None if r.get("ok") else (r.get("body") or r.get("error"))}
    props = {}
    for k, v in (("firstname", first_name), ("lastname", last_name),
                 ("company", company), ("phone", phone),
                 ("lifecyclestage", lifecycle_stage)):
        if v:
            props[k] = v
    if not props:
        raise ValueError("nothing to update — pass at least one field")
    r = await call("PATCH", f"/crm/v3/objects/contacts/{contact_id}",
                   body={"properties": props})
    return {"ok": r.get("ok"), "id": contact_id, "updated": list(props.keys()),
            "error": None if r.get("ok") else (r.get("body") or r.get("error"))}
