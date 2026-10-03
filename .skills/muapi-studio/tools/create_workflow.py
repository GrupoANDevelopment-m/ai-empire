"""Create a new MuAPI workflow (multi-step pipeline).

Mirrors createWorkflow + updateWorkflowName + deleteWorkflow from muapi.js.
Workflows are multi-node pipelines: e.g. "product photo → upscale → background
removal → ad copy → social post" all chained.

This is the most powerful abstraction in the MuAPI platform — you can compose
existing models into reusable automation.
"""
import os
import json
import urllib.request
from _http import MUAPI_BASE


def _muapi_req(method, path, body=None):
    """Direct call to MuAPI (workflow endpoint, not /api/v1)."""
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
    Manage workflows (create / rename / delete / inspect).

    inputs:
        action (str): "create" (default), "rename", "delete", "inspect"
        name (str): workflow name (for create/rename)
        workflow_id (str): required for rename/delete/inspect
        definition (dict): workflow graph for create (nodes + edges)
        nodes (list): optional simplified node list (alternative to definition)
        description (str): what the workflow does

    returns:
        For create: {"ok": True, "workflow_id": "..."}
        For rename: {"ok": True, "workflow_id": "...", "name": "..."}
        For delete: {"ok": True, "deleted": true}
        For inspect: {"ok": True, "workflow": {...}, "nodes": [...], "inputs": [...]}
    """
    action = inputs.get("action") or "create"

    if action == "create":
        name = inputs.get("name")
        if not name:
            return {"ok": False, "error": "name required for create"}

        if inputs.get("definition"):
            body = {"name": name, "definition": inputs["definition"]}
        elif isinstance(inputs.get("nodes"), list):
            body = {"name": name, "nodes": inputs["nodes"]}
        else:
            return {"ok": False, "error": "definition or nodes list required for create"}
        if inputs.get("description"):
            body["description"] = inputs["description"]

        data, err = _muapi_req("POST", "/workflow/create", body)
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": data.get("id") or data.get("workflow_id"),
                "workflow": data}

    if action == "rename":
        wid = inputs.get("workflow_id")
        new_name = inputs.get("name")
        if not wid or not new_name:
            return {"ok": False, "error": "workflow_id and name required for rename"}
        data, err = _muapi_req("POST", f"/workflow/update-name/{wid}", {"name": new_name})
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "workflow_id": wid, "name": new_name}

    if action == "delete":
        wid = inputs.get("workflow_id")
        if not wid:
            return {"ok": False, "error": "workflow_id required for delete"}
        data, err = _muapi_req("DELETE", f"/workflow/delete-workflow-def/{wid}")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "deleted": True, "workflow_id": wid}

    if action == "inspect":
        wid = inputs.get("workflow_id")
        if not wid:
            return {"ok": False, "error": "workflow_id required for inspect"}
        defn, err1 = _muapi_req("GET", f"/workflow/get-workflow-def/{wid}")
        inputs_data, err2 = _muapi_req("GET", f"/workflow/{wid}/api-inputs")
        nodes_data, err3 = _muapi_req("GET", f"/workflow/{wid}/api-node-schemas")
        return {
            "ok": defn is not None,
            "workflow": defn or {},
            "inputs": inputs_data or [],
            "node_schemas": nodes_data or [],
            "errors": [e for e in (err1, err2, err3) if e],
        }

    return {"ok": False, "error": f"unknown action: {action}"}