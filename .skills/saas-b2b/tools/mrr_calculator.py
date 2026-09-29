"""MRR Calculator - calculates Monthly Recurring Revenue from customer list."""
def run(inputs):
    try:
        customers = inputs.get("customers", [])
        billing_period = inputs.get("billing_period", "monthly")
        if not isinstance(customers, list):
            return {"error": "customers must be a list"}

        total_mrr = 0.0
        by_plan = {}
        for c in customers:
            seats = float(c.get("seats", 0))
            price = float(c.get("price_per_seat", 0))
            plan = c.get("plan", "unknown")
            monthly_revenue = seats * price
            if billing_period == "annual":
                monthly_revenue = monthly_revenue / 12.0
            total_mrr += monthly_revenue
            by_plan[plan] = by_plan.get(plan, 0.0) + monthly_revenue

        return {
            "mrr": round(total_mrr, 2),
            "arr": round(total_mrr * 12, 2),
            "customer_count": len(customers),
            "by_plan": {k: round(v, 2) for k, v in by_plan.items()},
        }
    except Exception as e:
        return {"error": str(e)}
