"""create_deal — real CRM deal creation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend


async def create_deal(name: str, amount: float, pipeline: str = "default",
                      stage: str = "appointmentscheduled",
                      close_date: str = None, description: str = "") -> dict:
    """
    Create a CRM deal.

    Args:
        name: deal name (required)
        amount: deal value (required, > 0)
        pipeline: pipeline ID/name
        stage: deal stage
        close_date: ISO close date
        description: deal notes

    Returns:
        {"ok": True, "id": str, "deal": {...}}
    """
    if not name.strip():
        raise ValueError("name is required")
    if amount is None or float(amount) <= 0:
        raise ValueError("amount must be a positive number")
    if backend() == "salesforce":
        body = {"Name": name, "Amount": float(amount), "StageName": stage,
                "CloseDate": close_date, "Description": description}
        body = {k: v for k, v in body.items() if v}
        r = await call("POST", "/services/data/v60.0/sobjects/Opportunity", body=body)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "salesforce"}
        return {"ok": True, "id": r["body"]["id"], "backend": "salesforce",
                "deal": {"name": name, "amount": float(amount), "stage": stage}}
    props = {"dealname": name, "amount": str(amount), "dealstage": stage,
             "pipeline": pipeline, "description": description}
    if close_date:
        props["closedate"] = close_date
    r = await call("POST", "/crm/v3/objects/deals", body={"properties": props})
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "hubspot"}
    return {"ok": True, "id": r["body"]["id"], "backend": "hubspot",
            "deal": {"name": name, "amount": float(amount), "stage": stage}}
