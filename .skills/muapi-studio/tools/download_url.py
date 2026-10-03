"""Download a media file from a URL and return its content.

Mirrors downloadImage from packages/studio/src/utils/downloadImage.js.
Used to save generated media into AI Empire's storage (so the URL can expire
but the content is preserved).

Returns base64-encoded content with metadata (MIME type, filename).
"""
import base64
import urllib.request
import urllib.parse


def run(inputs):
    """
    Download a media file from a URL.

    inputs:
        url (str): required — source URL
        filename (str): optional — target filename (default: derived from URL)
        max_bytes (int): max download size (default: 100 MB)

    returns:
        {"ok": True, "filename": "...", "mime_type": "...",
         "size": N, "data_base64": "..."}
    """
    url = inputs.get("url")
    if not url:
        return {"ok": False, "error": "url required"}

    max_bytes = int(inputs.get("max_bytes") or 100 * 1024 * 1024)

    filename = inputs.get("filename")
    if not filename:
        path = urllib.parse.urlparse(url).path
        filename = path.rsplit("/", 1)[-1] or "download.bin"
    filename = filename.replace("/", "_").replace("\\", "_").strip() or "download.bin"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Empire/muapi-studio/3.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            content_type = r.headers.get("Content-Type") or "application/octet-stream"
            data = r.read()
            if len(data) > max_bytes:
                return {"ok": False, "error": f"file too large: {len(data)} > {max_bytes}"}
            if "." not in filename:
                ext_map = {
                    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
                    "image/gif": "gif", "video/mp4": "mp4", "audio/mpeg": "mp3",
                    "audio/wav": "wav", "audio/ogg": "ogg", "application/json": "json",
                }
                ext = ext_map.get(content_type.split(";")[0].strip())
                if ext:
                    filename = f"{filename}.{ext}"

            return {
                "ok": True,
                "url": url,
                "filename": filename,
                "mime_type": content_type.split(";")[0].strip(),
                "size": len(data),
                "data_base64": base64.b64encode(data).decode("ascii"),
            }
    except Exception as e:
        return {"ok": False, "error": f"download failed: {e}"}