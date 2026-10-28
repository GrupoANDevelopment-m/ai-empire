"""post_linkedin — real LinkedIn UGC post."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _social import token_for, normalize, ENDPOINTS, browser_fallback


async def post_linkedin(text: str, author_id: str = None,
                        visibility: str = "PUBLIC",
                        link_url: str = None, link_title: str = None) -> dict:
    """
    Publish a post to LinkedIn via the UGC API.

    Args:
        text: post body (max 3000 chars)
        author_id: urn:li:organization:<id> or urn:li:person:<id> (from LINKEDIN_AUTHOR_ID)
        visibility: PUBLIC | CONNECTIONS | MEMBERS
        link_url: optional article/link URL
        link_title: optional link title

    Returns:
        {"ok": True, "id": str, "url": str}
    """
    if not text.strip():
        raise ValueError("text is required")
    if len(text) > 3000:
        raise ValueError("LinkedIn post max 3000 chars")
    if visibility not in ("PUBLIC", "CONNECTIONS", "MEMBERS"):
        raise ValueError("visibility must be PUBLIC, CONNECTIONS or MEMBERS")

    author = author_id or os.getenv("LINKEDIN_AUTHOR_ID")
    if not author:
        raise RuntimeError("Set LINKEDIN_AUTHOR_ID (urn:li:organization:<id>)")

    body = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "visibility": visibility,
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "ARTICLE" if link_url else "NONE",
            }
        },
    }
    if link_url:
        body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [{
            "status": "READY", "originalUrl": link_url,
            "title": {"text": link_title or ""}}]

    h = token_for("linkedin")["LINKEDIN_TOKEN"]
    h = {"Authorization": f"Bearer {h}", "Content-Type": "application/json",
         "X-Restli-Protocol-Version": "2.0.0"}
    r = await __import__("importlib").util.spec_from_file_location(
        "sm_api2", "/workspace/ai-empire/.skills/_shared/api.py")
    m = __import__("importlib").util.module_from_spec(r); r.loader.exec_module(m)
    res = await m.request("POST", ENDPOINTS["linkedin"]["posts"], headers=h, json_body=body)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("body") or res.get("error"),
                "platform": "linkedin"}
    rid = (res.get("headers", {}).get("x-restli-id")
           or res.get("headers", {}).get("x-linkedin-id") or "")
    return {"ok": True, "id": rid, "platform": "linkedin",
            "url": f"https://www.linkedin.com/feed/update/{rid}" if rid else None,
            "chars": len(text)}
