"""Execute a pre-built workflow template.

Mirrors executeWorkflow from Open Generative AI's WorkflowStudio.
Workflows are multi-step pipelines (e.g. "product photo → ad → social post").
"""
from _http import request, poll_result


def run(inputs):
    """
    Execute a workflow by ID.

    inputs:
        workflow_id (str): required — workflow to run
        inputs (dict): parameters for the workflow (workflow-specific schema)
        wait (bool): default True

    returns:
        {"ok": True, "run_id": "...", "result": {...}}
    """
    workflow_id = inputs.get("workflow_id")
    if not workflow_id:
        return {"ok": False, "error": "workflow_id required"}

    wf_inputs = inputs.get("inputs") or {}

    result = request("POST", f"/api/v1/workflows/{workflow_id}/execute",
                    body={"inputs": wf_inputs}, timeout=30)
    if not result["ok"]:
        return result

    submit = result.get("data", {})
    run_id = submit.get("run_id") or submit.get("id") or submit.get("request_id")

    if not run_id:
        return {"ok": True, "result": submit, "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "run_id": run_id, "status": "submitted"}

    polled = poll_result(run_id,
                         int(inputs.get("poll_max_attempts") or 300),
                         int(inputs.get("poll_interval_ms") or 3000))
    if not polled["ok"]:
        return {"ok": False, "run_id": run_id, "error": polled["error"]}

    return {
        "ok": True,
        "run_id": run_id,
        "result": polled["data"],
        "workflow_id": workflow_id,
    }