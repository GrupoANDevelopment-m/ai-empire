"""list_deals — real CRM deal listing."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend, norm_deal


async def list_deals(stage: str = None, limit: int = 50) -> dict:
    """
    List CRM deals.

    Args:
        stage: optional stage filter (e.g. "qualifiedtobuy")
        limit: maximum deals

    Returns:
        {"ok": True, "count": int, "deals": [{id,name,amount,stage}]}
    """
    if backend() == "salesforce":
        soql = "SELECT Id,Name,Amount,StageName,CloseDate,Probability FROM Opportunity"
        if stage:
            soql += f" WHERE StageName = '{stage}'"
        soql += f" ORDER BY CreatedDate DESC LIMIT {limit}"
        r = await call("GET", "/services/data/v60.0/query", params={"q": soql})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "salesforce"}
        rows = r["body"].get("records", [])
        return {"ok": True, "count": len(rows), "backend": "salesforce",
                "deals": [norm_deal(x) for x in rows]}
    props = ["dealname", "amount", "dealstage", "closedate", "pipeline"]
    r = await call("GET", "/crm/v3/objects/deals",
                   params={"limit": limit, "properties": ",".join(props)})
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "backend": "hubspot"}
    rows = r["body"].get("results", [])
    if stage:
        rows = [x for x in rows if x.get("properties", {}).get("dealstage") == stage]
    return {"ok": True, "count": len(rows), "backend": "hubspot",
            "deals": [norm_deal(x) for x in rows]}
