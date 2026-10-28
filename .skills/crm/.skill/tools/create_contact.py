"""create_contact — real CRM contact creation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend, norm_contact


async def create_contact(email: str, first_name: str = "", last_name: str = "",
                         company: str = "", phone: str = "",
                         lifecycle_stage: str = "lead") -> dict:
    """
    Create a CRM contact.

    Args:
        email: contact email (required, must contain @)
        first_name: given name
        last_name: family name
        company: company name
        phone: phone number
        lifecycle_stage: lead | customer | opportunity

    Returns:
        {"ok": True, "id": str, "contact": {...}, "backend": str}
    """
    if not email or "@" not in email:
        raise ValueError(f"valid email required, got: {email!r}")

    if backend() == "salesforce":
        body = {"Email": email, "FirstName": first_name, "LastName": last_name,
                "Phone": phone, "Company": company, "LeadSource": "AI Empire"}
        r = await call("POST", "/services/data/v60.0/sobjects/Contact", body=body)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "salesforce"}
        r2 = await call("GET", f"/services/data/v60.0/sobjects/Contact/{r['body']['id']}")
        return {"ok": True, "id": r["body"]["id"], "backend": "salesforce",
                "contact": norm_contact(r2["body"]) if r2.get("ok") else body}

    props = {"email": email, "firstname": first_name, "lastname": last_name,
             "company": company, "phone": phone, "lifecyclestage": lifecycle_stage}
    props = {k: v for k, v in props.items() if v}
    r = await call("POST", "/crm/v3/objects/contacts", body={"properties": props})
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "hubspot"}
    return {"ok": True, "id": r["body"]["id"], "backend": "hubspot",
            "contact": norm_contact(r["body"])}
