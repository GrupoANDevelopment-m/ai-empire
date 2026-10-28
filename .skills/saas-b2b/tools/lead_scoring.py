"""lead_scoring — deterministic ICP scoring (real math, explained factors)."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_ce = importlib.util.spec_from_file_location(
    "ce", os.path.join(os.path.dirname(os.path.abspath(__file__)), "company_enrichment.py"))
_ce_m = importlib.util.module_from_spec(_ce); _ce.loader.exec_module(_ce_m)


async def lead_scoring(domain: str, job_title: str = "",
                       enrich: bool = True, icp_min_employees: int = 20,
                       icp_max_employees: int = 5000,
                       target_industries: list = None) -> dict:
    """
    Score a lead 0-100 against an ICP, with a transparent factor breakdown.

    Args:
        domain: company domain (required)
        job_title: contact job title (seniority signal)
        enrich: fetch real firmographics first
        icp_min_employees / icp_max_employees: target company size
        target_industries: list of ICP industry keywords

    Returns:
        {"ok": True, "score": int, "grade": str, "factors": [{name,points,detail}],
         "data_used": {...}}
    """
    if not domain.strip():
        raise ValueError("domain is required")

    data = {}
    if enrich:
        e = await _ce_m.company_enrichment(domain, include_contacts=False)
        if e.get("ok"):
            data = e

    factors = []
    emp = data.get("employees")
    if emp:
        if icp_min_employees <= emp <= icp_max_employees:
            factors.append({"name": "company_size", "points": 25,
                            "detail": f"{emp} employees is inside ICP range "
                                      f"{icp_min_employees}-{icp_max_employees}"})
        elif emp > icp_max_employees:
            factors.append({"name": "company_size", "points": 8,
                            "detail": f"{emp} employees is larger than target max "
                                      f"{icp_max_employees}"})
        else:
            factors.append({"name": "company_size", "points": 6,
                            "detail": f"{emp} employees is below ICP minimum "
                                      f"{icp_min_employees}"})
    else:
        factors.append({"name": "company_size", "points": 0,
                        "detail": "employee count unavailable — no enrichment source"})

    ind = (data.get("industry") or "").lower()
    if target_industries:
        hit = next((t for t in target_industries if t.lower() in ind or
                    t.lower() in (data.get("description") or "").lower()), None)
        factors.append({"name": "industry_fit", "points": 25 if hit else 0,
                        "detail": f"matched {hit!r}" if hit else
                                  f"no match against {target_industries}"})
    else:
        factors.append({"name": "industry_fit", "points": 15,
                        "detail": "no ICP industry list given — neutral points"})

    t = (job_title or "").lower()
    seniority = 25 if re.search(r"\b(chief|c[toefpmo]|vp|vice president|founder|owner|"
                                r"director|head of|partner|president)\b", t) else 0
    factors.append({"name": "seniority", "points": seniority,
                    "detail": f"title {job_title!r} -> "
                              f"{'decision maker' if seniority else 'non-decision-maker'}"})

    loc = data.get("country")
    factors.append({"name": "location", "points": 10 if loc else 0,
                    "detail": f"country={loc}" if loc else "country unknown"})

    growth = 10 if data.get("founded_year") and (2026 - data["founded_year"]) <= 10 else 0
    factors.append({"name": "recency", "points": growth,
                    "detail": f"founded {data.get('founded_year')}"
                              if data.get("founded_year") else "founding year unknown"})

    has_site = bool(data.get("domain"))
    factors.append({"name": "web_presence", "points": 10 if has_site else 0,
                    "detail": "site reachable" if has_site else "site unreachable"})

    score = max(0, min(100, sum(f["points"] for f in factors)))
    grade = ("A" if score >= 75 else "B" if score >= 55 else
             "C" if score >= 35 else "D")
    return {"ok": True, "score": score, "grade": grade,
            "domain": domain, "factors": factors,
            "data_used": {"employees": emp, "industry": data.get("industry"),
                          "country": loc, "founded_year": data.get("founded_year"),
                          "source": data.get("source", "none")},
            "caveat": "score reflects only the signals listed in 'factors'"}
