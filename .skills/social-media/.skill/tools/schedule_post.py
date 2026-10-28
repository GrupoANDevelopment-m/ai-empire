"""schedule_post — persist a scheduled post queue (real DB/file, not fake)."""
import sys, os, json, uuid, sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB = Path(os.getenv("EMPIRE_POST_QUEUE_DB",
                    "/workspace/ai-empire/data/post_queue.db"))


def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB))
    c.execute("""CREATE TABLE IF NOT EXISTS scheduled_posts (
        id TEXT PRIMARY KEY, platform TEXT, content TEXT,
        scheduled_at TEXT, status TEXT DEFAULT 'scheduled',
        created_at TEXT, posted_id TEXT, error TEXT)""")
    c.commit()
    return c


async def schedule_post(platform: str, content: str,
                        scheduled_at: str) -> dict:
    """
    Queue a post for later publication.

    Args:
        platform: linkedin | twitter | facebook | instagram
        content: the post text
        scheduled_at: ISO datetime for publication

    Returns:
        {"ok": True, "id": str, "scheduled_at": str, "db": str}
    """
    if not platform.strip():
        raise ValueError("platform is required")
    if not content.strip():
        raise ValueError("content is required")
    try:
        dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("scheduled_at must be ISO format, e.g. 2026-10-25T14:00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt <= datetime.now(timezone.utc):
        raise ValueError("scheduled_at must be in the future")

    pid = f"post_{uuid.uuid4().hex[:12]}"
    c = _conn()
    try:
        c.execute("INSERT INTO scheduled_posts "
                  "(id,platform,content,scheduled_at,created_at) VALUES (?,?,?,?,?)",
                  (pid, platform.lower(), content, dt.isoformat(),
                   datetime.now(timezone.utc).isoformat()))
        c.commit()
    finally:
        c.close()
    return {"ok": True, "id": pid, "platform": platform.lower(),
            "scheduled_at": dt.isoformat(), "db": str(DB)}


async def due_posts(now: str = None) -> dict:
    """List queued posts whose time has come."""
    now = now or datetime.now(timezone.utc).isoformat()
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id,platform,content,scheduled_at FROM scheduled_posts "
            "WHERE status='scheduled' AND scheduled_at<=? ORDER BY scheduled_at",
            (now,)).fetchall()
        return {"ok": True, "count": len(rows),
                "due": [{"id": r[0], "platform": r[1], "preview": r[2][:80],
                         "scheduled_at": r[3]} for r in rows],
                "db": str(DB)}
    finally:
        c.close()
