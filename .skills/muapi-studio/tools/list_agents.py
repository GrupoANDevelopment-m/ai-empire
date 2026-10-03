"""Browse and fetch MuAPI agents (pre-built assistants).

Mirrors getTemplateAgents + getUserAgents + getPublishedAgents + getAgentBySlug
+ getUserConversations + getAgentConversation from muapi.js.
"""
import os
import json
import urllib.request
from _http import MUAPI_BASE


def _muapi_get(path):
    """Direct GET to MuAPI (no /api/v1 prefix)."""
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
    Browse and fetch agents + conversations.

    inputs:
        scope (str): "template" (default), "user", "published", or "conversations"
        agent_slug (str): if set, fetch specific agent details
        conversation_id (str): if set with agent_slug, fetch specific conversation

    returns:
        {"ok": True, "agents": [...]} or
        {"ok": True, "agent": {...}} or
        {"ok": True, "conversations": [...]} or
        {"ok": True, "conversation": {...}}
    """
    scope = inputs.get("scope") or "template"
    agent_slug = inputs.get("agent_slug")
    conversation_id = inputs.get("conversation_id")

    if agent_slug and conversation_id:
        data, err = _muapi_get(f"/agents/by-slug/{agent_slug}/{conversation_id}")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "conversation": data,
                "agent_slug": agent_slug, "conversation_id": conversation_id}

    if agent_slug:
        data, err = _muapi_get(f"/agents/by-slug/{agent_slug}")
        if err:
            return {"ok": False, "error": err}
        return {"ok": True, "agent": data, "slug": agent_slug}

    if scope == "conversations":
        data, err = _muapi_get("/agents/user/conversations")
        if err:
            return {"ok": False, "error": err}
        if not isinstance(data, list):
            data = []
        return {"ok": True, "conversations": data, "count": len(data)}

    if scope == "template":
        path = "/agents/templates/agents"
    elif scope == "user":
        path = "/agents/user/agents"
    elif scope == "published":
        path = "/agents/featured/agents"
    else:
        return {"ok": False, "error": f"unknown scope: {scope}"}

    data, err = _muapi_get(path)
    if err:
        return {"ok": False, "error": err}

    items = data if isinstance(data, list) else (
        data.get("agents") or data.get("items") or data.get("results") or [])
    return {"ok": True, "scope": scope, "agents": items, "count": len(items)}