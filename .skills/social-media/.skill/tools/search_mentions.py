"""search_mentions — real mention search (X API + Instagram mentions)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for, normalize


async def search_mentions(platform: str, query: str = None,
                          account_id: str = None, max_results: int = 25) -> dict:
    """
    Find real mentions/replies for an account.

    Args:
        platform: twitter | instagram
        query: override the search query
        account_id: account id (defaults to env)
        max_results: maximum mentions

    Returns:
        {"ok": True, "platform": str, "count": int, "mentions": [{id,text,author}]}
    """
    p = normalize(platform)
    if p not in ("twitter", "instagram"):
        raise ValueError("LinkedIn/Facebook do not expose a free mentions "
                         "endpoint; use the browser automation skill instead")
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "sm_api8", "/workspace/ai-empire/.skills/_shared/api.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

    if p == "twitter":
        uid = account_id or os.getenv("TWITTER_USER_ID")
        if not uid:
            raise RuntimeError("Set TWITTER_USER_ID")
        q = query or f"@{os.getenv('TWITTER_USERNAME', '')} -is:retweet"
        if not query and not os.getenv("TWITTER_USERNAME"):
            raise RuntimeError("Set TWITTER_USERNAME or pass an explicit query")
        r = await m.request("GET", "https://api.twitter.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {token_for('twitter')['TWITTER_TOKEN']}"},
            params={"query": q, "max_results": min(max_results, 100),
                    "tweet.fields": "created_at,public_metrics,author_id"})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
        rows = r["body"].get("data") or []
        return {"ok": True, "platform": p, "query": q, "count": len(rows),
                "mentions": [{"id": t["id"], "text": t.get("text", "")[:140],
                              "created_at": t.get("created_at"),
                              "metrics": t.get("public_metrics", {})} for t in rows]}

    uid = account_id or os.getenv("INSTAGRAM_USER_ID")
    if not uid:
        raise RuntimeError("Set INSTAGRAM_USER_ID")
    tok = token_for("instagram")["INSTAGRAM_TOKEN"]
    r = await m.request("GET",
        f"https://graph.facebook.com/v19.0/{uid}/mentions",
        params={"fields": "text,media,from,id,timestamp,username", "access_token": tok})
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
    rows = r["body"].get("data", [])
    return {"ok": True, "platform": p, "count": len(rows),
            "mentions": [{"id": x.get("id"), "text": (x.get("text") or "")[:140],
                          "username": x.get("username"),
                          "timestamp": x.get("timestamp")} for x in rows[:max_results]]}
