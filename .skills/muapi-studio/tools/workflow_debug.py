"""Workflow debug — run individual nodes, check run status.

Mirrors runSingleNode + getNodeStatus + getNodeSchemas + deleteNodeRun.
Lets the LLM debug a workflow by running one node at a time, or check
the status of an in-progress workflow run.
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
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"API {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)[:200]


def run(inputs):
    """
    Debug a workflow by running individual nodes or checking run status.

    inputs:
        action (str): "run_node" (default), "status", "delete_run"
        workflow_id (str): required for run_node
        node_id (str): required for run_node
        payload (dict): input for run_node
        run_id (str): required for status and delete_run
        node_run_id (str): required for delete_run

    returns:
        {"ok": True, "result": {...}} or
        {"ok": True, "status": "..."} or
        {"ok": True, "deleted": true}
    """
    action = inputs.get("action") or "run_node"

    if action == "run_node":
        wid = inputs.get("workflow_id")
        nid = inputs.get("node_id")
        if not wid or not nid:
            return {"ok": False, "error": "workflow_id and node_id required"}
        payload = inputs.get("payload") or {}
        data, err = _muapi_req("POST", f"/workflow/{wid}/node/{nid}/run", payload)
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "action": "run_node", "node_run_id": data.get("id"),
                "result": data}

    if action == "status":
        run_id = inputs.get("run_id")
        if not run_id:
            return {"ok": False, "error": "run_id required for status"}
        data, err = _muapi_req("GET", f"/workflow/run/{run_id}/status")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "action": "status", "run_id": run_id, "status": data}

    if action == "delete_run":
        node_run_id = inputs.get("node_run_id")
        if not node_run_id:
            return {"ok": False, "error": "node_run_id required"}
        data, err = _muapi_req("DELETE", f"/workflow/node-run/{node_run_id}")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "action": "delete_run", "node_run_id": node_run_id,
                "deleted": True}

    return {"ok": False, "error": f"unknown action: {action}"}