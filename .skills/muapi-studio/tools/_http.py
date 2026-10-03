"""
HTTP helper for MuAPI.

Uses urllib (no extra deps) and respects MUAPI_API_KEY from env.
"""
import os
import json
import time
import urllib.request
import urllib.error
import ssl


MUAPI_BASE = os.getenv("MUAPI_BASE_URL", "https://api.muapi.ai")


def _api_key():
    """Read API key from env. Returns None if missing."""
    return os.getenv("MUAPI_API_KEY")


def _has_api_key():
    """Check if API key is configured."""
    return bool(_api_key())


def request(method, path, body=None, timeout=30):
    """Make an HTTP request to MuAPI. Returns parsed JSON or raises."""
    key = _api_key()
    if not key:
        return {
            "ok": False,
            "error": "MUAPI_API_KEY not configured — set it in .env or tenant config",
        }

    url = f"{MUAPI_BASE}{path}"
    headers = {
        "x-api-key": key,
        "Content-Type": "application/json",
        "User-Agent": "AI-Empire/muapi-studio/1.0",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    # Don't verify SSL in sandboxed env (cert chain issue), but document it
    ctx = ssl.create_default_context()
    if os.getenv("MUAPI_INSECURE_SSL") == "1":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return {
                "ok": True,
                "status": r.status,
                "data": json.loads(r.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "status": e.code,
            "error": f"API {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}",
        }
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Network: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def poll_result(request_id, max_attempts=120, interval_ms=2000):
    """Poll /api/v1/predictions/{id}/result until ready.
    Mirrors the Open Generative AI client behavior.
    """
    if not request_id:
        return {"ok": False, "error": "no request_id"}

    interval_s = interval_ms / 1000.0
    for attempt in range(1, max_attempts + 1):
        result = request(
            "POST",
            f"/api/v1/predictions/{request_id}/result",
            body={},
            timeout=10,
        )
        if not result["ok"]:
            # Network blip — retry
            time.sleep(interval_s)
            continue

        data = result.get("data", {})
        status = (data.get("status") or "").lower()

        if status in ("completed", "succeeded", "success"):
            return {"ok": True, "data": data, "attempts": attempt}
        if status in ("failed", "error"):
            return {"ok": False, "error": data.get("error", "generation failed"),
                    "data": data, "attempts": attempt}

        # Still processing — wait
        time.sleep(interval_s)

    return {"ok": False, "error": f"timeout after {max_attempts} attempts"}


def extract_output_url(data):
    """Normalize response to always have 'url' populated.
    Mirrors muapi.js normalize() in Open Generative AI.
    """
    if not isinstance(data, dict):
        return None
    outputs = data.get("outputs") or []
    if outputs and isinstance(outputs, list):
        return outputs[0]
    return data.get("url") or (data.get("output") or {}).get("url")