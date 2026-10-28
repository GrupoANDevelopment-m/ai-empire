"""update_deal_stage — real pipeline stage move."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _crm import call, backend

STAGES = {
    "hubspot": ["appointmentscheduled", "qualifiedtobuy", "presentationscheduled",
                "decisionmakerboughtin", "contractsent", "closedwon", "closedlost"],
    "salesforce": ["Prospecting", "Qualification", "Needs Analysis", "Value Proposition",
                   "Id. Decision Makers", "Perception Analysis", "Proposal/Price Quote",
                   "Negotiation/Review", "Closed Won", "Closed Lost"],
}


async def update_deal_stage(deal_id: str, stage: str) -> dict:
    """
    Move a deal to a new pipeline stage.

    Args:
        deal_id: the deal ID
        stage: target stage

    Returns:
        {"ok": True, "deal_id": str, "stage": str, "valid_stages": [...]}
    """
    if not deal_id or not stage:
        raise ValueError("deal_id and stage are required")
    key = "salesforce" if backend() == "salesforce" else "hubspot"
    valid = STAGES[key]
    if valid and stage not in valid:
        raise ValueError(f"invalid stage {stage!r}. Valid: {', '.join(valid)}")
    if backend() == "salesforce":
        r = await call("PATCH", f"/services/data/v60.0/sobjects/Opportunity/{deal_id}",
                       body={"StageName": stage})
    else:
        r = await call("PATCH", f"/crm/v3/objects/deals/{deal_id}",
                       body={"properties": {"dealstage": stage}})
    return {"ok": r.get("ok"), "deal_id": deal_id, "stage": stage,
            "valid_stages": valid,
            "error": None if r.get("ok") else (r.get("body") or r.get("error"))}
