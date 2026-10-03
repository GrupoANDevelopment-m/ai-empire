"""Browse community-published workflows and agents as starting templates.

Mirrors Open Generative AI's WorkflowStudio + AgentStudio.
Templates are pre-built compositions you can execute immediately.

Use cases:
- "Find a workflow that turns product photos into Instagram Reels"
- "List all marketing agents"
- "Get the schema for workflow X"
"""
from _http import request


def run(inputs):
    """
    Browse and fetch templates (workflows or agents).

    inputs:
        kind (str): "workflows" or "agents" (default: "workflows")
        scope (str): "template" (community templates, default) or "published"
                    or "user" (your own — requires auth to fetch)
        workflow_id (str): if set, fetch the schema/data for this specific workflow
        agent_slug (str): if set with kind="agents", fetch a specific agent

    returns:
        {"ok": True, "items": [...]}
        or for specific workflow:
        {"ok": True, "workflow": {...}, "nodes": [...]}
    """
    kind = inputs.get("kind") or "workflows"
    scope = inputs.get("scope") or "template"

    if kind == "workflows":
        if inputs.get("workflow_id"):
            wid = inputs["workflow_id"]
            data_res = request("GET", f"/api/v1/workflows/{wid}", timeout=15)
            nodes_res = request("GET", f"/api/v1/workflows/{wid}/node-schemas", timeout=15)
            return {
                "ok": True,
                "workflow": data_res.get("data", {}) if data_res["ok"] else {},
                "nodes": nodes_res.get("data", []) if nodes_res["ok"] else [],
            }

        if scope == "template":
            path = "/api/v1/workflows/templates"
        elif scope == "published":
            path = "/api/v1/workflows/published"
        else:
            path = "/api/v1/workflows/user"

    elif kind == "agents":
        if inputs.get("agent_slug"):
            slug = inputs["agent_slug"]
            res = request("GET", f"/api/v1/agents/{slug}", timeout=15)
            return {"ok": res["ok"], "agent": res.get("data", {}),
                    "error": res.get("error")}

        if scope == "template":
            path = "/api/v1/agents/templates"
        elif scope == "published":
            path = "/api/v1/agents/published"
        else:
            path = "/api/v1/agents/user"

    else:
        return {"ok": False, "error": f"unknown kind: {kind} (use workflows or agents)"}

    result = request("GET", path, timeout=15)
    if not result["ok"]:
        return result

    data = result.get("data", {})
    items = data if isinstance(data, list) else (
        data.get("items") or data.get("workflows") or
        data.get("agents") or data.get("results") or [])

    return {
        "ok": True,
        "kind": kind,
        "scope": scope,
        "items": items,
        "count": len(items),
    }