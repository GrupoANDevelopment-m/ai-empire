"""Creative agent (Open-AI-Design-Agent backend) — full session/job operations.

Real production endpoints. Backed by https://api.muapi.ai/api/v1/creative-agent/*
via the proxy pattern from Anil-matcha/Open-AI-Design-Agent.
"""
import os
import json
import urllib.request
import urllib.parse
from _http import MUAPI_BASE


def _muapi_call(method, path, body=None, params=None, timeout=30):
    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key: return None, "MUAPI_API_KEY not configured"
    if path.startswith("/api/v1/"):
        base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
        url = f"{base}{path}"
    else:
        url = f"{MUAPI_BASE}/{path.lstrip('/')}"
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

    if action == "list_sessions":
        data, err = _muapi_call("GET", "/api/v1/creative-agent/sessions")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "sessions": data}

    if action == "create_session":
        payload = inputs.get("payload") or {"name": inputs.get("name", "New Session")}
        data, err = _muapi_call("POST", "/api/v1/creative-agent/sessions", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session": data}

    if action == "get_session_messages":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        data, err = _muapi_call("GET", f"/api/v1/creative-agent/sessions/{sid}/messages")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "messages": data}

    if action == "update_session_messages":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        payload = inputs.get("payload") or {"messages": inputs.get("messages", [])}
        data, err = _muapi_call("PATCH", f"/api/v1/creative-agent/sessions/{sid}/messages", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "data": data}

    if action == "rename_session":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        new_name = inputs.get("name")
        if not new_name: return {"ok": False, "error": "name required"}
        data, err = _muapi_call("PATCH", f"/api/v1/creative-agent/sessions/{sid}", body={"name": new_name})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "name": new_name}

    if action == "delete_session":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        data, err = _muapi_call("DELETE", f"/api/v1/creative-agent/sessions/{sid}")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "deleted": True}

    if action == "chat":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        message = inputs.get("message")
        if not message: return {"ok": False, "error": "message required"}
        payload = inputs.get("payload") or {
            "message": message,
            "attachments": inputs.get("attachments") or [],
        }
        data, err = _muapi_call("POST", f"/api/v1/creative-agent/sessions/{sid}/chat", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "result": data}

    if action == "get_session_assets":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        data, err = _muapi_call("GET", f"/api/v1/creative-agent/sessions/{sid}/assets")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "assets": data}

    if action == "register_session_asset":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        payload = inputs.get("payload") or {
            "url": inputs.get("url"),
            "kind": inputs.get("kind", "image"),
            "name": inputs.get("name"),
        }
        data, err = _muapi_call("POST", f"/api/v1/creative-agent/sessions/{sid}/assets", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "asset": data}

    if action == "get_session_jobs":
        sid = inputs.get("session_id")
        if not sid: return {"ok": False, "error": "session_id required"}
        data, err = _muapi_call("GET", f"/api/v1/creative-agent/sessions/{sid}/jobs")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "jobs": data}

    if action == "run_skill":
        sid = inputs.get("session_id")
        skill = inputs.get("skill")
        if not sid: return {"ok": False, "error": "session_id required"}
        if not skill: return {"ok": False, "error": "skill required"}
        payload = inputs.get("payload") or {
            "skill": skill,
            "inputs": inputs.get("inputs") or {},
        }
        data, err = _muapi_call("POST", f"/api/v1/creative-agent/sessions/{sid}/run-skill", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "session_id": sid, "skill": skill, "result": data}

    if action == "approve_job":
        jid = inputs.get("job_id")
        if not jid: return {"ok": False, "error": "job_id required"}
        data, err = _muapi_call("POST", f"/api/v1/creative-agent/jobs/{jid}/approve", body=inputs.get("payload") or {})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "job_id": jid, "approved": True, "data": data}

    if action == "reject_job":
        jid = inputs.get("job_id")
        if not jid: return {"ok": False, "error": "job_id required"}
        payload = inputs.get("payload") or ({"reason": inputs["reason"]} if inputs.get("reason") else {})
        data, err = _muapi_call("POST", f"/api/v1/creative-agent/jobs/{jid}/reject", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "job_id": jid, "rejected": True, "data": data}

    if action == "cancel_job":
        jid = inputs.get("job_id")
        if not jid: return {"ok": False, "error": "job_id required"}
        data, err = _muapi_call("POST", f"/api/v1/creative-agent/jobs/{jid}/cancel")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "job_id": jid, "cancelled": True, "data": data}

    if action == "get_job_status":
        jid = inputs.get("job_id")
        if not jid: return {"ok": False, "error": "job_id required"}
        data, err = _muapi_call("GET", f"/api/v1/creative-agent/jobs/{jid}/status")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "job_id": jid, "status": data}

    if action == "get_job_events":
        jid = inputs.get("job_id")
        if not jid: return {"ok": False, "error": "job_id required"}
        params = inputs.get("params") or {}
        if "since" in inputs: params["since"] = inputs["since"]
        data, err = _muapi_call("GET", f"/api/v1/creative-agent/jobs/{jid}/events", params=params)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "job_id": jid, "events": data}

    if action == "list_agent_skills":
        data, err = _muapi_call("GET", "/api/v1/creative-agent/agent-skills")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "skills": data}

    if action == "account_balance":
        data, err = _muapi_call("GET", "/api/v1/account/balance")
        if err: return {"ok": False, "error": err}
        balance = (data.get("balance") or data.get("credits") or
                   data.get("available_credits") or data.get("amount") or 0)
        return {"ok": True, "balance": balance, "raw": data}

    return {"ok": False, "error": f"unknown action: {action}"}
