"""post_twitter — real X/Twitter v2 post (with optional thread)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for


async def post_twitter(text: str, reply_to_tweet_id: str = None) -> dict:
    """
    Publish a tweet via the X API v2.

    Args:
        text: tweet body (max 280 chars for free tier)
        reply_to_tweet_id: make this a reply

    Returns:
        {"ok": True, "id": str, "text": str}
    """
    if not text.strip():
        raise ValueError("text is required")
    if len(text) > 280:
        raise ValueError(f"tweet is {len(text)} chars, max 280. Use post_thread()")
    h = {"Authorization": f"Bearer {token_for('twitter')['TWITTER_TOKEN']}",
         "Content-Type": "application/json"}
    body = {"text": text}
    if reply_to_tweet_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "sm_api3", "/workspace/ai-empire/.skills/_shared/api.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    r = await m.request("POST", "https://api.twitter.com/2/tweets",
                        headers=h, json_body=body)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"),
                "platform": "twitter"}
    return {"ok": True, "id": r["body"].get("data", {}).get("id"),
            "text": text, "platform": "twitter"}
