"""reply_to_mention — real reply to a mention."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_pt = importlib.util.spec_from_file_location(
    "rm_pt", os.path.join(os.path.dirname(os.path.abspath(__file__)), "post_twitter.py"))
_pt_m = importlib.util.module_from_spec(_pt); _pt.loader.exec_module(_pt_m)
from _social import token_for


async def reply_to_mention(mention_id: str, reply_text: str,
                           platform: str = "twitter") -> dict:
    """
    Reply to a mention/reply on a real account.

    Args:
        mention_id: the parent post/mention ID
        reply_text: reply body
        platform: twitter | instagram

    Returns:
        {"ok": True, "id": str, "reply_to": str}
    """
    if not mention_id.strip():
        raise ValueError("mention_id is required")
    if not reply_text.strip():
        raise ValueError("reply_text is required")

    if platform.lower() == "twitter":
        r = await _pt_m.post_twitter(reply_text, reply_to_tweet_id=mention_id)
        return {"ok": r.get("ok"), "id": r.get("id"), "reply_to": mention_id,
                "platform": "twitter",
                "error": r.get("error")}

    if platform.lower() == "instagram":
        uid = os.getenv("INSTAGRAM_USER_ID")
        if not uid:
            raise RuntimeError("Set INSTAGRAM_USER_ID")
        tok = token_for("instagram")["INSTAGRAM_TOKEN"]
        import importlib.util
        s = importlib.util.spec_from_file_location(
            "sm_api9", "/workspace/ai-empire/.skills/_shared/api.py")
        m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
        r = await m.request("POST", f"https://graph.facebook.com/v19.0/{uid}/comments",
            json_body={"message": reply_text, "access_token": tok})
        return {"ok": r.get("ok"), "id": (r.get("body") or {}).get("id"),
                "reply_to": mention_id, "platform": "instagram",
                "error": None if r.get("ok") else (r.get("body") or r.get("error"))}

    raise ValueError("LinkedIn comments require an approved Community Management "
                     "app; use browser automation instead of faking an API call")
