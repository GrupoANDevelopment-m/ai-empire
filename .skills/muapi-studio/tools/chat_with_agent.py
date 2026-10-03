"""Chat with a pre-built MuAPI agent.

Mirrors sendAgentChatMessage + pollAgentChatResult from muapi.js.
Agents are pre-configured assistants on the MuAPI platform — like GPTs, each
with a specific purpose (marketing copy, code review, image prompting, etc).

Returns a full conversation envelope with messages.
"""
import os
import json
import urllib.request
import time
from _http import MUAPI_BASE, request as _api_request


def _poll_agent_chat(request_id, max_attempts=150, interval_ms=2000):
    """Poll until the agent turn is complete (is_complete=true).

    Mirrors pollAgentChatResult from muapi.js.
    """
    interval_s = interval_ms / 1000.0
    for attempt in range(1, max_attempts + 1):
        result = _api_request("POST", f"/api/v1/predictions/{request_id}/result",
                              body={}, timeout=10)
        if result["ok"]:
            data = result.get("data", {})
            if data.get("is_complete"):
                return {"ok": True, "data": data, "attempts": attempt}
            if data.get("status") in ("failed", "error"):
                return {"ok": False, "error": data.get("error", "agent chat failed"),
                        "data": data, "attempts": attempt}
        time.sleep(interval_s)
    return {"ok": False, "error": f"timeout after {max_attempts} attempts"}


def run(inputs):
    """
    Send a message to a MuAPI agent and get the reply.

    inputs:
        agent_slug (str): required — agent identifier (e.g. "marketing-copywriter")
        message (str): required — your message
        conversation_id (str): optional — continue an existing conversation
        attachments (list): optional — file URLs to attach
        wait (bool): default True — poll until agent replies

    returns:
        {"ok": True, "request_id": "...", "conversation_id": "...",
         "messages": [...], "is_complete": True}
    """
    agent_slug = inputs.get("agent_slug")
    message = inputs.get("message")

    if not agent_slug:
        return {"ok": False, "error": "agent_slug required"}
    if not message:
        return {"ok": False, "error": "message required"}

    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "MUAPI_API_KEY not configured"}

    payload = {
        "message": message,
        "conversation_id": inputs.get("conversation_id") or None,
        "attachments": inputs.get("attachments") or None,
        "stream": False,
    }

    # Send via MuAPI's chat endpoint (not /api/v1)
    base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
    url = f"{base}/agents/by-slug/{agent_slug}/chat"
    req = urllib.request.Request(
        url, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            submit = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"chat send: API {e.code} {e.read().decode()[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"chat send: {e}"}

    request_id = submit.get("request_id") or submit.get("id")
    if not request_id:
        return {"ok": True, "result": submit, "sync": True}

    if inputs.get("wait") is False:
        return {"ok": True, "request_id": request_id, "status": "submitted"}

    polled = _poll_agent_chat(request_id,
                              int(inputs.get("poll_max_attempts") or 150),
                              int(inputs.get("poll_interval_ms") or 2000))
    if not polled["ok"]:
        return {"ok": False, "request_id": request_id, "error": polled["error"]}

    data = polled["data"]
    return {
        "ok": True,
        "request_id": request_id,
        "conversation_id": data.get("conversation_id"),
        "messages": data.get("messages") or [],
        "is_complete": data.get("is_complete", True),
        "attempts": polled["attempts"],
    }