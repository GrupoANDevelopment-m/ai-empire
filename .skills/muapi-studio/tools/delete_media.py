"""Delete a generated media item.

Mirrors deleteMedia from muapi.js. Removes the media file from MuAPI storage
(via DELETE /api/v1/predictions/{request_id}/media). Useful for cleaning up
after a failed batch or removing content the user no longer wants.
"""
from _http import request


def run(inputs):
    """
    Delete generated media.

    inputs:
        request_id (str): required — the request_id from a previous generation

    returns:
        {"ok": True, "deleted": true, "request_id": "..."}
    """
    request_id = inputs.get("request_id")
    if not request_id:
        return {"ok": False, "error": "request_id required"}

    result = request("DELETE", f"/api/v1/predictions/{request_id}/media", timeout=15)
    if not result["ok"]:
        return result

    return {"ok": True, "deleted": True, "request_id": request_id}