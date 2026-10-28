"""get_followers — real follower/audience counts."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for, normalize


async def get_followers(platform: str, account_id: str = None) -> dict:
    """
    Fetch real follower counts for a platform account.

    Args:
        platform: linkedin | twitter | facebook | instagram
        account_id: account id (defaults to env)

    Returns:
        {"ok": True, "platform": str, "followers": int, "following": int, "name": str}
    """
    p = normalize(platform)
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "sm_api7", "/workspace/ai-empire/.skills/_shared/api.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

    if p == "twitter":
        uid = account_id or os.getenv("TWITTER_USER_ID")
        if not uid:
            raise RuntimeError("Set TWITTER_USER_ID")
        r = await m.request("GET", f"https://api.twitter.com/2/users/{uid}",
            headers={"Authorization": f"Bearer {token_for('twitter')['TWITTER_TOKEN']}"},
            params={"user.fields": "public_metrics,description,username"})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
        d = r["body"].get("data", {})
        pm = d.get("public_metrics", {})
        return {"ok": True, "platform": p, "username": d.get("username"),
                "name": d.get("name"), "followers": pm.get("followers_count", 0),
                "following": pm.get("following_count", 0),
                "tweets": pm.get("tweet_count", 0)}

    pid = account_id or (os.getenv("INSTAGRAM_USER_ID") if p == "instagram"
                         else os.getenv("FACEBOOK_PAGE_ID"))
    if not pid:
        raise RuntimeError(f"Set {'INSTAGRAM_USER_ID' if p=='instagram' else 'FACEBOOK_PAGE_ID'}")
    tok = (token_for("instagram")["INSTAGRAM_TOKEN"] if p == "instagram"
           else token_for("facebook")["FACEBOOK_TOKEN"])
    fields = ("username,followers_count,media_count,biography" if p == "instagram"
              else "name,fan_count,followers_count,category")
    r = await m.request("GET", f"https://graph.facebook.com/v19.0/{pid}",
                        params={"fields": fields, "access_token": tok})
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
    b = r["body"]
    return {"ok": True, "platform": p, "name": b.get("name") or b.get("username"),
            "followers": b.get("followers_count", b.get("fan_count", 0)),
            "posts": b.get("media_count", 0),
            "bio": b.get("biography") or b.get("category")}

    raise ValueError(f"LinkedIn follower count requires a licensed API key "
                     f"(Marketing Developer tier); no free endpoint exists")
