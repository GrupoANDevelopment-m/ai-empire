"""Get generation history — list of past generations on MuAPI.

Mirrors getHistory. Useful for browsing past generations and reusing assets.
"""
from _http import request


def run(inputs):
    """
    List past generations.

    inputs:
        cursor (str): pagination cursor from a previous response
        limit (int): max items to return (default 50, max ~200)

    returns:
        {"ok": True, "items": [...], "next_cursor": "..."}
    """
    params = []
    if inputs.get("cursor"):
        params.append(f"cursor={inputs['cursor']}")
    limit = int(inputs.get("limit") or 50)
    params.append(f"limit={limit}")

    qs = "&".join(params)
    result = request("GET", f"/api/v1/history?{qs}", timeout=15)
    if not result["ok"]:
        return result

    data = result.get("data", {})
    if isinstance(data, list):
        items = data
    else:
        items = (data.get("history") or
                 data.get("items") or
                 data.get("results") or
                 data.get("data") or [])

    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "next_cursor": data.get("next_cursor") or data.get("cursor"),
        "raw": data if not isinstance(data, list) else None,
    }