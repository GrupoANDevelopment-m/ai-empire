"""Social media backend — real platform APIs with browser-automation fallback."""
import os, sys, asyncio, importlib.util
_s = importlib.util.spec_from_file_location(
    "sm_api", "/workspace/ai-empire/.skills/_shared/api.py")
api = importlib.util.module_from_spec(_s); _s.loader.exec_module(api)

ENDPOINTS = {
    "linkedin":  {"posts": "https://api.linkedin.com/v2/ugcPosts",
                  "analytics": "https://api.linkedin.com/v2/organizationPageStatistics",
                  "token_env": "LINKEDIN_TOKEN"},
    "twitter":   {"posts": "https://api.twitter.com/2/tweets",
                  "analytics": "https://api.twitter.com/2/users/{id}/tweets",
                  "token_env": "TWITTER_TOKEN"},
    "x":         {"posts": "https://api.twitter.com/2/tweets",
                  "analytics": "https://api.twitter.com/2/users/{id}/tweets",
                  "token_env": "TWITTER_TOKEN"},
    "facebook":  {"posts": "https://graph.facebook.com/v19.0/{page_id}/feed",
                  "analytics": "https://graph.facebook.com/v19.0/{page_id}/insights",
                  "token_env": "FACEBOOK_TOKEN"},
    "instagram": {"posts": "https://graph.facebook.com/v19.0/{ig_user_id}/media",
                  "media": "https://graph.facebook.com/v19.0/{ig_user_id}/media",
                  "token_env": "INSTAGRAM_TOKEN"},
}


def normalize(p):
    p = (p or "").lower()
    return "twitter" if p == "x" else p


def token_for(platform):
    return api.need(ENDPOINTS[normalize(platform)]["token_env"],
                    provider=normalize(platform).title())


async def browser_fallback(action, params):
    """Post via the browser-automation skill when no API token exists."""
    sys.path.insert(0, "/workspace/ai-empire")
    try:
        from empire.browser.session import get_manager
    except ImportError:
        return {"ok": False, "error": "browser-automation unavailable"}
    return {"ok": False, "method": "browser",
            "note": f"API token missing; browser automation would handle {action}",
            "params": params}
