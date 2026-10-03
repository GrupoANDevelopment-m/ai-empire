"""Agent library (Open-Poe-AI backend) — full agent operations.

Real production endpoints. Backed by https://api.muapi.ai/agents/* via the
proxy pattern from Anil-matcha/Open-Poe-AI.
"""
import os
import json
import urllib.request
import urllib.parse
from _http import MUAPI_BASE


def _muapi_call(method, path, body=None, params=None, timeout=30):
    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key: return None, "MUAPI_API_KEY not configured"
    base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
    url = f"{base}/{path.lstrip('/')}"
    if params: url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, method=method, data=data,
        headers={"Content-Type": "application/json", "x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            try: return json.loads(raw), None
            except ValueError: return {"raw": raw}, None
    except urllib.error.HTTPError as e:
        try: err_body = json.loads(e.read().decode("utf-8"))
        except Exception: err_body = {"detail": e.reason}
        return None, f"API {e.code}: {err_body.get('detail', err_body)}"
    except Exception as e:
        return None, str(e)[:200]


def run(inputs):
    action = inputs.get("action")
    if not action: return {"ok": False, "error": "action required"}

    if action == "suggest_agents":
        task = inputs.get("task") or inputs.get("prompt") or inputs.get("description")
        if not task: return {"ok": False, "error": "task required (describe what you want an agent to do)"}
        data, err = _muapi_call("POST", "/agents/suggest",
                                body=inputs.get("payload") or {"task": task})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "suggestions": data}

    if action == "update_agent":
        slug = inputs.get("slug") or inputs.get("agent_slug")
        if not slug: return {"ok": False, "error": "slug required"}
        payload = inputs.get("payload") or inputs.get("updates")
        if not payload: return {"ok": False, "error": "payload required (what to change)"}
        data, err = _muapi_call("PUT", f"/agents/by-slug/{slug}", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "slug": slug, "agent": data}

    if action == "like_agent":
        slug = inputs.get("slug") or inputs.get("agent_slug")
        if not slug: return {"ok": False, "error": "slug required"}
        params = {}
        if "liked" in inputs: params["liked"] = "true" if inputs["liked"] else "false"
        data, err = _muapi_call("POST", f"/agents/by-slug/{slug}/like", params=params)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "slug": slug, "data": data}

    if action == "get_agent_profile":
        slug = inputs.get("slug") or inputs.get("agent_slug")
        if not slug: return {"ok": False, "error": "slug required"}
        data, err = _muapi_call("GET", f"/agents/{slug}/profile")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "profile": data}

    if action == "get_agent_skills":
        data, err = _muapi_call("GET", "/agents/skills")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "skills": data}

    if action == "preview_realign":
        slug = inputs.get("slug") or inputs.get("agent_slug")
        if not slug: return {"ok": False, "error": "slug required"}
        payload = inputs.get("payload") or {"prompt": inputs.get("prompt", "Hello")}
        data, err = _muapi_call("POST", f"/agents/by-slug/{slug}/preview-realign", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "slug": slug, "preview": data}

    if action == "get_prediction_result":
        request_id = inputs.get("request_id")
        if not request_id: return {"ok": False, "error": "request_id required"}
        data, err = _muapi_call("GET", f"/api/v1/predictions/{request_id}/result")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "request_id": request_id, "result": data}

    if action == "flux_schnell_image":
        prompt = inputs.get("prompt")
        if not prompt: return {"ok": False, "error": "prompt required"}
        payload = inputs.get("payload") or {"prompt": prompt}
        data, err = _muapi_call("POST", "/api/v1/flux-schnell-image", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "result": data}

    if action == "get_signed_url":
        payload = inputs.get("payload") or {"path": inputs.get("path")}
        data, err = _muapi_call("POST", "/workflow/cloudfront-signed-url", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "signed_url_data": data}

    return {"ok": False, "error": f"unknown action: {action}"}
