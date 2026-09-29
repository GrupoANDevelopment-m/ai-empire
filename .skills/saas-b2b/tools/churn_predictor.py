"""Churn Predictor - predicts churn probability based on usage signals."""
def run(inputs):
    try:
        c = inputs.get("customer", {})
        signals = []
        score = 0.0

        logins = int(c.get("logins_last_30d", 0))
        if logins == 0:
            score += 0.35
            signals.append("sem logins nos ultimos 30 dias")
        elif logins < 3:
            score += 0.20
            signals.append(f"poucos logins ({logins})")

        features = int(c.get("features_used_last_30d", 0))
        if features == 0:
            score += 0.25
            signals.append("nenhuma feature usada")
        elif features < 3:
            score += 0.15
            signals.append(f"poucas features usadas ({features})")

        tickets = int(c.get("support_tickets_last_30d", 0))
        if tickets >= 5:
            score += 0.20
            signals.append(f"muitos tickets ({tickets})")
        elif tickets >= 2:
            score += 0.10

        nps = int(c.get("nps_score", 0))
        if nps < -30:
            score += 0.25
            signals.append(f"NPS detrator ({nps})")
        elif nps < 0:
            score += 0.10

        seats_used = int(c.get("seats_used", 0))
        seats_paid = int(c.get("seats_paid", 1))
        if seats_paid > 0:
            util = seats_used / seats_paid
            if util < 0.3:
                score += 0.15
                signals.append(f"subutilizacao de seats ({util:.0%})")

        days = int(c.get("days_since_signup", 365))
        if days < 30 and logins < 5:
            score += 0.10
            signals.append("novo cliente sem onboarding completo")

        score = min(score, 1.0)
        if score < 0.20:
            risk = "low"
        elif score < 0.50:
            risk = "medium"
        elif score < 0.75:
            risk = "high"
        else:
            risk = "critical"
        return {"churn_probability": round(score, 3), "risk_level": risk, "signals": signals}
    except Exception as e:
        return {"error": str(e)}
