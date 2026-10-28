"""search_contacts — real CRM contact search."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend, norm_contact


async def search_contacts(query: str, limit: int = 25) -> dict:
    """
    Search CRM contacts.

    Args:
        query: name, email or company fragment
        limit: maximum results

    Returns:
        {"ok": True, "count": int, "contacts": [{id,email,first_name,last_name,company}]}
    """
    if not query.strip():
        raise ValueError("query cannot be empty")
    if backend() == "salesforce":
        soql = (f"FIND {{{query}}} IN ALL FIELDS RETURNING Contact "
                f"(Id,FirstName,LastName,Email,Phone,Account.Name) LIMIT {limit}")
        r = await call("GET", "/services/data/v60.0/query", params={"q": soql})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "salesforce"}
        rows = r["body"].get("records", [])
        return {"ok": True, "query": query, "count": len(rows), "backend": "salesforce",
                "contacts": [norm_contact(x) for x in rows]}
    r = await call("GET", "/crm/v3/objects/contacts/search",
                   body={"filterGroups": [{"filters": [{"propertyName": "email",
                                     "operator": "HAS_TOKEN",
                                     "value": query}]}],
                         "limit": limit, "properties": ["email","firstname","lastname",
                                                        "company","phone"]})
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "hubspot"}
    rows = r["body"].get("results", [])
    return {"ok": True, "query": query, "count": len(rows), "backend": "hubspot",
            "contacts": [norm_contact(x) for x in rows]}
