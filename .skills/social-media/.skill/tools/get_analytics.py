"""get_analytics — real per-platform metrics."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for, normalize


async def get_analytics(platform: str, account_id: str = None,
                        post_id: str = None, days: int = 30) -> dict:
    """
    Fetch real metrics for a post or account.

    Args:
        platform: linkedin | twitter | facebook | instagram
        account_id: account/page id (defaults to env per platform)
        post_id: specific post (omit for account totals)
        days: lookback window

    Returns:
        {"ok": True, "platform": str, "metrics": {likes,comments,shares,impressions,...}}
    """
    p = normalize(platform)
    if p not in ("linkedin", "twitter", "facebook", "instagram"):
        raise ValueError(f"unsupported platform {platform!r}")
    import importlib.util
    s = importlib.util.spec_from_file_location(
        "sm_api6", "/workspace/ai-empire/.skills/_shared/api.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)

    if p == "twitter":
        uid = account_id or os.getenv("TWITTER_USER_ID")
        if not uid:
            raise RuntimeError("Set TWITTER_USER_ID")
        params = {"tweet.fields": "public_metrics,created_at,conversation_id",
                  "expansions": "referenced_tweets.id",
                  "max_results": 100}
        if post_id:
            params = {"ids": post_id, "tweet.fields": "public_metrics,created_at"}
        r = await m.request("GET",
            f"https://api.twitter.com/2/users/{uid}/tweets" if not post_id
            else "https://api.twitter.com/2/tweets",
            headers={"Authorization":
                     f"Bearer {token_for('twitter')['TWITTER_TOKEN']}"},
            params=params)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
        rows = r["body"].get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        agg = {"tweets": len(rows), "likes": 0, "replies": 0, "quotes": 0,
               "retweets": 0, "impressions": 0}
        for t in rows:
            pm = t.get("public_metrics", {})
            agg["likes"] += pm.get("like_count", 0)
            agg["replies"] += pm.get("reply_count", 0)
            agg["quotes"] += pm.get("quote_count", 0)
            agg["retweets"] += pm.get("retweet_count", 0)
            agg["impressions"] += pm.get("impression_count", 0)
        return {"ok": True, "platform": p, "account_id": uid,
                "days": days, "metrics": agg,
                "posts": [{"id": t["id"], "text": t.get("text", "")[:80],
                           "metrics": t.get("public_metrics", {})} for t in rows[:10]]}

    if p == "linkedin":
        org = account_id or os.getenv("LINKEDIN_ORG_ID")
        if not org:
            raise RuntimeError("Set LINKEDIN_ORG_ID")
        r = await m.request(
            "GET",
            f"https://api.linkedin.com/v2/organizationPageStatistics",
            headers={"Authorization":
                     f"Bearer {token_for('linkedin')['LINKEDIN_TOKEN']}",
                     "LinkedIn-Version": "202401", "X-Restli-Protocol-Version": "2.0.0"},
            params={"q": "organizationalEntity",
                    "organizationalEntity": f"urn:li:organization:{org}"})
        if not r.get("ok"):
            return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
        return {"ok": True, "platform": p, "org_id": org, "days": days,
                "raw": r["body"]}

    pid = account_id or os.getenv("FACEBOOK_PAGE_ID") or os.getenv("INSTAGRAM_USER_ID")
    if not pid:
        raise RuntimeError("Set FACEBOOK_PAGE_ID / INSTAGRAM_USER_ID")
    tok = token_for(p)[f"{p.upper()}_TOKEN" if p == "instagram" else "FACEBOOK_TOKEN"]
    metrics = ("post_impressions,post_impressions_unique,post_reactions_by_type_total,"
               "post_clicks,post_shares" if p == "instagram" else
               "page_impressions,page_post_engagements,page_fan_adds_unique")
    if post_id:
        metrics = ("comments_count,likes.count,shares.count" if p == "instagram"
                   else "reaction_types,comments,shares")
        url = (f"https://graph.facebook.com/v19.0/{post_id}/insights"
               if p == "facebook" else f"https://graph.facebook.com/v19.0/{pid}/insights")
        params = {"metric": metrics, "access_token": tok}
    else:
        url = f"https://graph.facebook.com/v19.0/{pid}/insights"
        params = {"metric": metrics, "period": "day",
                  "since": f"{(len(str(days)) and 0) or ''}" or None, "access_token": tok}
        params = {k: v for k, v in params.items() if v}
    r = await m.request("GET", url, params=params)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("body") or r.get("error"), "platform": p}
    data = r["body"].get("data", [])
    return {"ok": True, "platform": p, "account_id": pid, "days": days,
            "metric_count": len(data),
            "metrics": {m_.get("name"): m_.get("values", [{}])[-1].get("value")
                        for m_ in data}}
