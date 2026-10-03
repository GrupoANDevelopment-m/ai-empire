"""Inspect a workflow before executing it.

Mirrors getWorkflowInputs + getAllNodeSchemas + getNodeSchemas from muapi.js.
Lets the LLM know what inputs a workflow expects and what nodes it has.
"""
import os
import json
import urllib.request
from _http import MUAPI_BASE


def _muapi_get(path):
    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key:
        return None, "MUAPI_API_KEY not configured"
    base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
    url = f"{base}{path}"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json",
                                                "x-api-key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"API {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)[:200]


def run(inputs):
    """
    Get workflow metadata before running it.

    inputs:
        workflow_id (str): required
        include (str): "all" (default), "inputs", "nodes", "definition"

    returns:
        {"ok": True, "inputs": [...], "nodes": [...], "definition": {...}}
    """
    wid = inputs.get("workflow_id")
    if not wid:
        return {"ok": False, "error": "workflow_id required"}

    include = inputs.get("include") or "all"
    result = {"ok": True, "workflow_id": wid}

    if include in ("all", "inputs"):
        data, err = _muapi_get(f"/workflow/{wid}/api-inputs")
        result["inputs"] = data if data is not None else []
        if err: result["inputs_error"] = err

    if include in ("all", "nodes"):
        data, err = _muapi_get(f"/workflow/{wid}/api-node-schemas")
        result["nodes"] = data if data is not None else []
        if err: result["nodes_error"] = err

    if include in ("all", "definition"):
        data, err = _muapi_get(f"/workflow/get-workflow-def/{wid}")
        result["definition"] = data if data is not None else {}
        if err: result["definition_error"] = err

    return result