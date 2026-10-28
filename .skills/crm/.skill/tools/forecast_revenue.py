"""forecast_revenue — weighted pipeline forecast."""
import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_gp = importlib.util.spec_from_file_location(
    "fr_gp", os.path.join(os.path.dirname(os.path.abspath(__file__)), "get_pipeline.py"))
_gp_m = importlib.util.module_from_spec(_gp); _gp.loader.exec_module(_gp_m)

# default win probability by stage name (override with env JSON)
DEFAULT_P = {"appointment": 0.15, "qualif": 0.25, "present": 0.40,
             "decision": 0.60, "contract": 0.75, "sent": 0.75,
             "won": 1.0, "negotiation": 0.65, "review": 0.70,
             "proposal": 0.45, "analysis": 0.30, "prospecting": 0.10,
             "lost": 0.0}


async def forecast_revenue(quarter: str = None, probabilities: dict = None) -> dict:
    """
    Compute a weighted revenue forecast from the open pipeline.

    Args:
        quarter: optional label, e.g. "2026-Q4"
        probabilities: optional {stage_name_lower: win_probability} override

    Returns:
        {"ok": True, "open_pipeline": float, "weighted_forecast": float,
         "by_stage": [...], "confidence": str}
    """
    p = dict(DEFAULT_P)
    import os as _os, json as _json
    if _os.getenv("FORECAST_PROBABILITIES"):
        try:
            p.update({k.lower(): float(v) for k, v in
                      _json.loads(_os.environ["FORECAST_PROBABILITIES"]).items()})
        except Exception:
            pass
    if probabilities:
        p.update({k.lower(): float(v) for k, v in probabilities.items()})

    r = await _gp_m.get_pipeline(group_by="stage")
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}

    open_total = weighted = 0.0
    rows = []
    for s in r["stages"]:
        key = str(s["stage"]).lower()
        prob = p.get(key)
        if prob is None:
            prob = max((v for k, v in p.items() if k in key), default=0.3)
        w = s["value"] * prob
        open_total += s["value"]
        weighted += w
        rows.append({"stage": s["stage"], "count": s["count"],
                     "value": s["value"], "win_probability": round(prob, 2),
                     "weighted": round(w, 2)})

    conf = "high" if weighted and abs(weighted - open_total) / open_total > 0.4 else "medium"
    return {"ok": True,
            "quarter": quarter or f"{datetime.now(timezone.utc).year}-Q"
                                 f"{(datetime.now(timezone.utc).month - 1) // 3 + 1}",
            "open_pipeline": round(open_total, 2),
            "weighted_forecast": round(weighted, 2),
            "by_stage": rows, "confidence": conf,
            "deal_count": r["deal_count"], "backend": r.get("backend")}
