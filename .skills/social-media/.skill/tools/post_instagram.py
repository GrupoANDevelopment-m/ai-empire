"""post_instagram — real Instagram Graph API (two-stage: create container + publish)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for


async def post_instagram(caption: str, image_url: str = None,
                         image_path: str = None,
                         ig_user_id: str = None) -> dict:
    """
    Publish a feed post to Instagram (requires a Business/Creator account linked to a Page).

    Args:
        caption: post caption (max 2200 chars)
        image_url: publicly reachable image URL (required by Graph API)
        image_path: local file to upload as a data URI (alternative)
        ig_user_id: Instagram user ID (from INSTAGRAM_USER_ID)

    Returns:
        {"ok": True, "creation_id": str, "media_id": str, "permalink": str}
    """
    if not caption.strip():
        raise ValueError("caption is required")
    if len(caption) > 2200:
        raise ValueError(f"caption is {len(caption)} chars, max 2200")
    uid = ig_user_id or os.getenv("INSTAGRAM_USER_ID")
    if not uid:
        raise RuntimeError("Set INSTAGRAM_USER_ID")
    if not (image_url or image_path):
        raise ValueError("image_url or image_path is required (Instagram needs media)")

    if image_path and not image_url:
        import base64, mimetypes, pathlib
        p = pathlib.Path(image_path)
        if not p.exists():
            raise FileNotFoundError(f"image not found: {image_path}")
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        image_url = f"data:{mime};base64,{b64}"

    tok = token_for("instagram")["INSTAGRAM_TOKEN"]
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "sm_api5", "/workspace/ai-empire/.skills/_shared/api.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

    # Stage 1: create media container
    r1 = await m.request("POST", f"https://graph.facebook.com/v19.0/{uid}/media",
                         json_body={"image_url": image_url, "caption": caption,
                                    "access_token": tok})
    if not r1.get("ok"):
        return {"ok": False, "stage": "create_container",
                "error": r1.get("body") or r1.get("error")}
    cid = r1["body"].get("id")
    if not cid:
        return {"ok": False, "stage": "create_container",
                "error": "no creation id returned", "raw": r1["body"]}

    # Stage 2: publish
    r2 = await m.request("POST", f"https://graph.facebook.com/v19.0/{uid}/media_publish",
                         json_body={"creation_id": cid, "access_token": tok})
    if not r2.get("ok"):
        return {"ok": False, "stage": "publish", "creation_id": cid,
                "error": r2.get("body") or r2.get("error")}
    mid = r2["body"].get("id")
    return {"ok": True, "creation_id": cid, "media_id": mid,
            "permalink": f"https://instagram.com/p/{mid}" if mid else None,
            "platform": "instagram"}
