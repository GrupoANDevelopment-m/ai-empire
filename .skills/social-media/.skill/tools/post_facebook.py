"""post_facebook — real Facebook Page feed post."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for


async def post_facebook(message: str, page_id: str = None,
                        link: str = None) -> dict:
    """
    Publish to a Facebook Page feed.

    Args:
        message: post text
        page_id: Page ID (from FACEBOOK_PAGE_ID)
        link: optional link to share

    Returns:
        {"ok": True, "id": str, "url": str}
    """
    if not message.strip():
        raise ValueError("message is required")
    pid = page_id or os.getenv("FACEBOOK_PAGE_ID")
    if not pid:
        raise RuntimeError("Set FACEBOOK_PAGE_ID")
    h = {"Authorization": f"Bearer {token_for('facebook')['FACEBOOK_TOKEN']}"}
    body = {"message": message, "access_token": token_for("facebook")["FACEBOOK_TOKEN"]}
    if link:
        body["link"] = link
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "sm_api4", "/workspace/ai-empire/.skills/_shared/api.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    r = await m.request("POST", f"https://graph.facebook.com/v19.0/{pid}/feed",
                        headers=h, json_body=body)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"),
                "platform": "facebook"}
    pid_out = r["body"].get("post_id") or r["body"].get("id")
    return {"ok": True, "id": pid_out, "platform": "facebook",
            "url": f"https://facebook.com/{pid_out}" if pid_out else None}
