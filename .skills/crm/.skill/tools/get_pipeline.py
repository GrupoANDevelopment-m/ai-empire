"""get_pipeline — real pipeline aggregation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_ld = importlib.util.spec_from_file_location(
    "ld", os.path.join(os.path.dirname(os.path.abspath(__file__)), "list_deals.py"))
_ld_m = importlib.util.module_from_spec(_ld); _ld.loader.exec_module(_ld_m)


async def get_pipeline(group_by: str = "stage") -> dict:
    """
    Aggregate deals into a pipeline view.

    Args:
        group_by: "stage" or "owner"

    Returns:
        {"ok": True, "total_value": float, "deal_count": int, "stages": [...]}
    """
    r = await _ld_m.list_deals(limit=250)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    deals = r["deals"]

    buckets = {}
    for d in deals:
        k = str(d.get(group_by) or "unknown")
        b = buckets.setdefault(k, {"stage": k, "count": 0, "value": 0.0})
        b["count"] += 1
        try:
            b["value"] += float(d.get("amount") or 0)
        except (TypeError, ValueError):
            pass

    stages = sorted(buckets.values(), key=lambda x: -x["value"])
    for s in stages:
        s["value"] = round(s["value"], 2)
        s["avg"] = round(s["value"] / s["count"], 2) if s["count"] else 0

    return {"ok": True, "group_by": group_by, "deal_count": len(deals),
            "total_value": round(sum(s["value"] for s in stages), 2),
            "stages": stages, "backend": r.get("backend")}
