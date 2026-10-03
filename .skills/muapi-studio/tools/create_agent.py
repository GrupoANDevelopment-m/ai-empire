"""Create a new MuAPI agent (pre-built assistant).

Mirrors createAgent from muapi.js. POST /agents with the agent definition.

An "agent" on MuAPI is a configurable assistant with:
- A system prompt defining its role
- Optional model selection
- Tool/function calling capabilities
- Streaming support

Useful for: building reusable specialists (e.g. "social media copywriter",
"image prompt engineer") that you or your team can chat with repeatedly.
"""
import os
import json
import urllib.request
from _http import MUAPI_BASE


def run(inputs):
    """
    Create a new MuAPI agent.

    inputs:
        name (str): required — agent display name
        slug (str): required — URL-safe identifier
        description (str): what the agent does
        system_prompt (str): required — the agent's persona + instructions
        model (str): optional LLM model (default: provider's default)
        is_public (bool): make agent public (default False)
        tools (list): optional list of tool names to enable

    returns:
        {"ok": True, "agent": {...}, "id": "...", "slug": "..."}
    """
    name = inputs.get("name")
    slug = inputs.get("slug")
    system_prompt = inputs.get("system_prompt")

    if not name:
        return {"ok": False, "error": "name required"}
    if not slug:
        return {"ok": False, "error": "slug required"}
    if not system_prompt:
        return {"ok": False, "error": "system_prompt required"}

    payload = {
        "name": name,
        "slug": slug,
        "system_prompt": system_prompt,
    }
    if inputs.get("description"):
        payload["description"] = inputs["description"]
    if inputs.get("model"):
        payload["model"] = inputs["model"]
    if "is_public" in inputs:
        payload["is_public"] = bool(inputs["is_public"])
    if isinstance(inputs.get("tools"), list):
        payload["tools"] = inputs["tools"]

    api_key = os.getenv("MUAPI_API_KEY")
    if not api_key:
        return {"ok": False, "error": "MUAPI_API_KEY not configured"}

    base = MUAPI_BASE.rsplit("/api/v1", 1)[0]
    url = f"{base}/agents"
    req = urllib.request.Request(
        url, method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"API {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    return {
        "ok": True,
        "agent": data,
        "id": data.get("id"),
        "slug": data.get("slug") or slug,
    }