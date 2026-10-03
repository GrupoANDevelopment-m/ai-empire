"""Register or list interest in beta MuAPI apps.

Mirrors registerAppInterest + getAppInterests from muapi.js. Lets you:
- Sign up for early access to upcoming apps/features
- See which apps you've already expressed interest in

The "apps" are typically upcoming products or features on the MuAPI platform.
"""
import os
import json
import urllib.request
from _http import MUAPI_BASE


def _muapi_req(method, path, body=None):
    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key:
        return None, "MUAPI_API_KEY not configured"
    base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
    url = f"{base}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"API {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)[:200]


def run(inputs):
    """
    Register or list beta app interests.

    inputs:
        action (str): "register" (default) or "list"
        app_name (str): required for "register" — the app name to sign up for

    returns:
        For register: {"ok": True, "app_name": "...", "registered": true}
        For list: {"ok": True, "interests": [...]}
    """
    action = inputs.get("action") or "register"

    if action == "register":
        app_name = inputs.get("app_name")
        if not app_name:
            return {"ok": False, "error": "app_name required for register"}
        data, err = _muapi_req("POST", "/app/interest", {"app_name": app_name})
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "app_name": app_name, "registered": True, "data": data}

    if action == "list":
        data, err = _muapi_req("GET", "/app/interests")
        if err:
            return {"ok": False, "error": err}
        if not isinstance(data, list):
            data = []
        return {"ok": True, "interests": data, "count": len(data)}

    return {"ok": False, "error": f"unknown action: {action}"}