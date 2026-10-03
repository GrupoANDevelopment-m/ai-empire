"""Check account credit balance on MuAPI.

Mirrors getUserBalance. Read-only — returns current credit balance.
Useful to check before launching expensive jobs.
"""
from _http import request


def run(inputs):
    """
    Get current MuAPI credit balance.

    inputs: (none)

    returns:
        {"ok": True, "balance": 1234.5, "currency": "credits", "raw": {...}}
    """
    result = request("GET", "/api/v1/account/balance", timeout=15)
    if not result["ok"]:
        return result

    data = result.get("data", {})
    balance = (data.get("balance") or
               data.get("credits") or
               data.get("available_credits") or
               data.get("amount") or 0)
    return {
        "ok": True,
        "balance": balance,
        "raw": data,
    }