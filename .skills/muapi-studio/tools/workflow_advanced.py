"""Advanced workflow operations (Vibe Workflow backend).

Real production endpoints. Backed by https://api.muapi.ai/workflow/* via the
same proxy pattern used in Vibe-Workflow/server (SamurAIGPT/Vibe-Workflow).

This adds Vibe-Workflow-specific endpoints to the muapi-studio skill:
  publish_workflow, template_workflow, cloudfront_signed_url, generate_thumbnail,
  get_workflow_last_run, architect_workflow, poll_architect_result,
  get_workflow_api_outputs, update_workflow_category, calculate_dynamic_cost,
  get_file_upload_url.
"""
import os
import json
import urllib.request
import urllib.parse
import time
from _http import MUAPI_BASE


def _muapi_call(method, path, body=None, params=None, timeout=30):
    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key:
        return None, "MUAPI_API_KEY not configured"
    base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
    url = f"{base}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, method=method, data=data,
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            try:
                return json.loads(raw), None
            except ValueError:
                return {"raw": raw}, None
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"detail": e.reason}
        return None, f"API {e.code}: {err_body.get('detail', err_body)}"
    except Exception as e:
        return None, str(e)[:200]


def run(inputs):
    action = inputs.get("action")
    if not action:
        return {"ok": False, "error": "action required"}

    if action == "publish_workflow":
        wid = inputs.get("workflow_id")
        if not wid: return {"ok": False, "error": "workflow_id required"}
        data, err = _muapi_call("POST", f"/workflow/workflow/{wid}/publish",
                                body=inputs.get("payload") or {})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": wid, "published": True, "data": data}

    if action == "template_workflow":
        wid = inputs.get("workflow_id")
        if not wid: return {"ok": False, "error": "workflow_id required"}
        data, err = _muapi_call("POST", f"/workflow/workflow/{wid}/template",
                                body=inputs.get("payload") or {})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": wid, "templated": True, "data": data}

    if action == "cloudfront_signed_url":
        data, err = _muapi_call("POST", "/workflow/cloudfront-signed-url",
                                body=inputs.get("payload") or {})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "signed_url": data}

    if action == "generate_thumbnail":
        wid = inputs.get("workflow_id")
        if not wid: return {"ok": False, "error": "workflow_id required"}
        data, err = _muapi_call("POST", f"/workflow/{wid}/thumbnail",
                                body=inputs.get("payload") or {})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": wid, "thumbnail": data}

    if action == "get_workflow_last_run":
        wid = inputs.get("workflow_id")
        if not wid: return {"ok": False, "error": "workflow_id required"}
        data, err = _muapi_call("GET", f"/workflow/get-workflow-last-run/{wid}")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": wid, "last_run": data}

    if action == "architect_workflow":
        prompt = inputs.get("prompt") or inputs.get("description")
        if not prompt:
            return {"ok": False, "error": "prompt required (describe what the workflow should do)"}
        payload = inputs.get("payload") or {"prompt": prompt}
        data, err = _muapi_call("POST", "/workflow/architect", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "result": data,
                "next_action": "poll_architect_result with the returned id"}

    if action == "poll_architect_result":
        aid = inputs.get("architect_id") or inputs.get("id")
        if not aid: return {"ok": False, "error": "architect_id required"}
        data, err = _muapi_call("GET", f"/workflow/poll-architect/{aid}/result")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "architect_id": aid, "result": data}

    if action == "get_workflow_api_outputs":
        run_id = inputs.get("run_id")
        if not run_id: return {"ok": False, "error": "run_id required"}
        data, err = _muapi_call("GET", f"/workflow/run/{run_id}/api-outputs")
        if err: return {"ok": False, "error": err}
        return {"ok": True, "run_id": run_id, "outputs": data}

    if action == "update_workflow_category":
        wid = inputs.get("workflow_id")
        if not wid: return {"ok": False, "error": "workflow_id required"}
        data, err = _muapi_call("POST", f"/workflow/update-category/{wid}",
                                body=inputs.get("payload") or {})
        if err: return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": wid, "data": data}

    if action == "calculate_dynamic_cost":
        payload = inputs.get("payload")
        if not payload: return {"ok": False, "error": "payload required (with task_name + params)"}
        data, err = _muapi_call("POST", "/app/calculate_dynamic_cost", body=payload)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "cost_data": data}

    if action == "get_file_upload_url":
        params = inputs.get("params") or {}
        if inputs.get("purpose"): params["purpose"] = inputs["purpose"]
        if inputs.get("content_type"): params["content_type"] = inputs["content_type"]
        data, err = _muapi_call("GET", "/app/get_file_upload_url", params=params)
        if err: return {"ok": False, "error": err}
        return {"ok": True, "upload_data": data}

    return {"ok": False, "error": f"unknown action: {action}"}


def architect_workflow_and_wait(inputs, max_attempts=60, interval_s=3):
    submit = run({**inputs, "action": "architect_workflow"})
    if not submit.get("ok"):
        return submit
    result = submit.get("result") or {}
    aid = result.get("id") or result.get("request_id") or result.get("architect_id")
    if not aid:
        return {"ok": True, "result": result, "note": "no id to poll"}
    for attempt in range(1, max_attempts + 1):
        polled = run({"action": "poll_architect_result", "architect_id": aid})
        if not polled.get("ok"):
            time.sleep(interval_s)
            continue
        data = polled.get("result") or {}
        status = (data.get("status") or "").lower()
        if status in ("completed", "succeeded", "success"):
            return {"ok": True, "result": data, "attempts": attempt}
        if status in ("failed", "error"):
            return {"ok": False, "error": data.get("error", "architect failed"), "data": data}
        time.sleep(interval_s)
    return {"ok": False, "error": f"timeout after {max_attempts} attempts"}
