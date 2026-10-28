"""post_thread — real multi-tweet thread."""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_pt = importlib.util.spec_from_file_location(
    "th_pt", os.path.join(os.path.dirname(os.path.abspath(__file__)), "post_twitter.py"))
_pt_m = importlib.util.module_from_spec(_pt); _pt.loader.exec_module(_pt_m)


def split_thread(text: str, max_len: int = 270) -> list:
    """Split a long text into tweet-sized chunks on sentence/word boundaries."""
    parts, cur = [], ""
    for para in text.split("\n\n"):
        for sent in [s for s in para.replace("\n", " ").split(". ") if s.strip()]:
            sent = sent.strip()
            piece = sent if sent.endswith(".") else sent + "."
            while len(piece) > max_len:
                cut = piece.rfind(" ", 0, max_len)
                cut = cut if cut > 0 else max_len
                parts.append(piece[:cut].strip())
                piece = piece[cut:].strip()
            if len(cur) + len(piece) + 1 <= max_len:
                cur = (cur + " " + piece).strip()
            else:
                if cur:
                    parts.append(cur)
                cur = piece
    if cur:
        parts.append(cur)
    return parts


async def post_thread(text: str, delay_seconds: int = 3) -> dict:
    """
    Publish a multi-tweet thread, chaining each reply to the previous.

    Args:
        text: full thread text
        delay_seconds: pause between posts (avoids rate limits)

    Returns:
        {"ok": True, "tweets": [{id,text}], "count": int}
    """
    chunks = split_thread(text)
    if not chunks:
        raise ValueError("nothing to post")
    if len(chunks) > 25:
        raise ValueError(f"thread has {len(chunks)} parts, max 25")
    posted, prev_id = [], None
    for i, c in enumerate(chunks):
        r = await _pt_m.post_twitter(c, reply_to_tweet_id=prev_id)
        if not r.get("ok"):
            return {"ok": False, "posted": len(posted), "total": len(chunks),
                    "failed_at": i, "error": r.get("error"),
                    "tweets": posted}
        posted.append({"id": r["id"], "text": c[:60]})
        prev_id = r["id"]
        if i < len(chunks) - 1 and delay_seconds:
            await asyncio.sleep(delay_seconds)
    return {"ok": True, "count": len(posted), "tweets": posted,
            "platform": "twitter"}
