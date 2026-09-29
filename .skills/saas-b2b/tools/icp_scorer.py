"""ICP Scorer - scores a lead against the SaaS B2B Ideal Customer Profile."""
SENIOR_ROLES = {
    "ceo": 30, "cto": 30, "cfo": 28, "coo": 28, "cmo": 25,
    "vp": 25, "vice president": 25, "director": 20, "head": 22,
    "manager": 15, "lead": 12, "senior": 8, "engineer": 5,
}
TARGET_INDUSTRIES = {
    "saas": 25, "fintech": 22, "edtech": 20, "healthtech": 22,
    "ecommerce": 18, "logistics": 18, "retail": 15, "consulting": 12,
    "manufacturing": 10, "agency": 8,
}
TARGET_COUNTRIES = {
    "BR": 20, "US": 18, "MX": 18, "PT": 16, "ES": 14,
    "AR": 12, "CL": 12, "CO": 12,
}


def run(inputs):
    try:
        lead = inputs.get("lead", {})
        score = 0
        reasons = []

        role = (lead.get("role") or "").lower().strip()
        role_pts = 0
        for key, pts in SENIOR_ROLES.items():
            if key in role:
                role_pts = max(role_pts, pts)
                break
        score += role_pts
        if role_pts >= 25:
            reasons.append(f"cargo senior ({role})")

        size = int(lead.get("company_size", 0))
        if size >= 500:
            size_pts, size_label = 25, "enterprise"
        elif size >= 100:
            size_pts, size_label = 20, "mid-market"
        elif size >= 20:
            size_pts, size_label = 15, "SMB+"
        elif size >= 5:
            size_pts, size_label = 8, "SMB"
        else:
            size_pts, size_label = 0, "muito pequeno"
        score += size_pts
        if size_pts >= 15:
            reasons.append(f"porte {size_label}")

        industry = (lead.get("industry") or "").lower().strip()
        ind_pts = TARGET_INDUSTRIES.get(industry, 0)
        score += ind_pts
        if ind_pts >= 18:
            reasons.append(f"setor prioritario ({industry})")

        country = (lead.get("country") or "").upper().strip()
        country_pts = TARGET_COUNTRIES.get(country, 5)
        score += country_pts
        if country_pts >= 16:
            reasons.append(f"mercado alvo ({country})")

        score = min(score, 100)
        tier = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"
        return {"score": score, "tier": tier, "reasons": reasons}
    except Exception as e:
        return {"error": str(e)}
