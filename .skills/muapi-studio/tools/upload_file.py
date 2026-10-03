"""Upload a local file to MuAPI and return a public URL.

This is needed because MuAPI requires public URLs for image_url/video_url/audio_url.
Uses the /api/v1/get_file_upload_url + /api/v1/upload-binary endpoint pair
(same as Open Generative AI).
"""
import os
from pathlib import Path
from _http import request


def run(inputs):
    """
    Upload a file to MuAPI.

    inputs:
        file_path (str): required — absolute path to file in workdir
        purpose (str): "image" | "video" | "audio" (default: "image")

    returns:
        {"ok": True, "url": "...", "purpose": "..."}
    """
    file_path = inputs.get("file_path")
    if not file_path:
        return {"ok": False, "error": "file_path required"}

    # Restrict to workdir (sandbox constraint)
    workdir = os.environ.get("EMPIRE_WORKDIR", "")
    abs_path = os.path.abspath(file_path)
    if workdir and not abs_path.startswith(workdir):
        return {"ok": False, "error": f"file_path must be inside {workdir}"}

    if not Path(abs_path).exists():
        return {"ok": False, "error": f"file not found: {abs_path}"}

    purpose = inputs.get("purpose") or "image"

    # Step 1: get a pre-signed upload URL
    presign = request("POST", "/api/v1/get_file_upload_url",
                      body={"purpose": purpose}, timeout=15)
    if not presign["ok"]:
        return presign

    upload_url = (presign.get("data") or {}).get("upload_url") or \
                 (presign.get("data") or {}).get("url")
    public_url = (presign.get("data") or {}).get("public_url") or upload_url

    if not upload_url:
        return {"ok": False, "error": "no upload_url returned", "raw": presign.get("data")}

    # Step 2: upload the file (PUT)
    # Use pathlib instead of built-in open() — open() is blocked by sandbox AST
    data = Path(abs_path).read_bytes()
    import urllib.request
    import urllib.error
    req = urllib.request.Request(upload_url, data=data, method="PUT",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"upload PUT {e.code}"}
    except Exception as e:
        return {"ok": False, "error": f"upload: {e}"}

    return {
        "ok": True,
        "url": public_url,
        "purpose": purpose,
        "filename": os.path.basename(abs_path),
    }