"""Empire Worker — real background worker.

Processes the persistent post queue (the same SQLite database the
social-media ``schedule_post`` tool writes to) and publishes due posts
through the real platform tools. It also performs scheduled maintenance
on the local audit log.

Nothing here is simulated: a post is published through the actual
LinkedIn / Twitter / Facebook / Instagram APIs, and the row is updated
with the real post id or the real error. When credentials are missing the
post is retried a bounded number of times and then marked failed with the
error that actually occurred.

Usage:
    python3 -m empire.worker                 # run forever
    python3 -m empire.worker --once          # drain the queue once
    python3 -m empire.worker --interval 30   # poll every 30 seconds
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "empire").is_dir() and (p / ".skills").is_dir())

log = logging.getLogger("empire.worker")

QUEUE_DB = Path(os.getenv("EMPIRE_POST_QUEUE_DB",
                           f"{_ROOT}/data/post_queue.db"))
MAX_ATTEMPTS = int(os.getenv("EMPIRE_WORKER_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = int(os.getenv("EMPIRE_WORKER_RETRY_BACKOFF", "60"))

PLATFORM_TOOL = {
    "linkedin": "social_media__post_linkedin",
    "twitter": "social_media__post_twitter",
    "facebook": "social_media__post_facebook",
    "instagram": "social_media__post_instagram",
}


def _connect() -> sqlite3.Connection:
    QUEUE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(QUEUE_DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS scheduled_posts (
        id TEXT PRIMARY KEY, platform TEXT, content TEXT,
        scheduled_at TEXT, status TEXT DEFAULT 'scheduled',
        created_at TEXT, posted_id TEXT, error TEXT,
        attempts INTEGER DEFAULT 0)""")
    conn.commit()
    return conn


def _ensure_attempts_column(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(scheduled_posts)")}
    if "attempts" not in cols:
        conn.execute("ALTER TABLE scheduled_posts ADD COLUMN attempts INTEGER DEFAULT 0")
        conn.commit()


def due_posts(now: datetime | None = None) -> list[dict]:
    """Return queued posts whose scheduled time has arrived."""
    now = now or datetime.now(timezone.utc)
    conn = _connect()
    try:
        _ensure_attempts_column(conn)
        rows = conn.execute(
            "SELECT id, platform, content, scheduled_at, COALESCE(attempts, 0) "
            "FROM scheduled_posts WHERE status='scheduled' AND scheduled_at<=? "
            "ORDER BY scheduled_at",
            (now.isoformat(),)).fetchall()
        return [{"id": r[0], "platform": r[1], "content": r[2],
                 "scheduled_at": r[3], "attempts": r[4]} for r in rows]
    finally:
        conn.close()


def _mark(conn: sqlite3.Connection, post_id: str, status: str,
          posted_id: str | None = None, error: str | None = None,
          attempts: int | None = None) -> None:
    if attempts is None:
        conn.execute(
            "UPDATE scheduled_posts SET status=?, posted_id=?, error=? WHERE id=?",
            (status, posted_id, error, post_id))
    else:
        conn.execute(
            "UPDATE scheduled_posts SET status=?, posted_id=?, error=?, "
            "attempts=?, scheduled_at=? WHERE id=?",
            (status, posted_id, error, attempts,
             (datetime.now(timezone.utc)
              + __import__("datetime").timedelta(
                  seconds=RETRY_BACKOFF_SECONDS)).isoformat(),
             post_id))
    conn.commit()


async def publish_post(post: dict) -> dict:
    """Publish one queued post through the real platform tool."""
    tool_name = PLATFORM_TOOL.get(post["platform"])
    if not tool_name:
        return {"ok": False,
                "error": f"unsupported platform: {post['platform']}"}

    from empire.agent.llm.dynamic_tools import resolve_tool_call
    from empire.agent.llm.tools import execute_tool

    info = resolve_tool_call(tool_name)
    if info is None:
        return {"ok": False, "error": f"tool not found: {tool_name}"}

    raw = await execute_tool(tool_name, {"text": post["content"]})
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        result = {"ok": False, "error": str(raw)[:300]}
    return result if isinstance(result, dict) else {"ok": False,
                                                     "error": str(result)[:300]}


async def process_due_posts() -> dict:
    """Publish every due post. Returns a real summary."""
    posts = due_posts()
    summary = {"checked": len(posts), "published": 0, "failed": 0,
               "retrying": 0, "details": []}
    if not posts:
        return summary

    conn = _connect()
    try:
        _ensure_attempts_column(conn)
        for post in posts:
            result = await publish_post(post)
            if result.get("ok"):
                _mark(conn, post["id"], "published",
                      posted_id=str(result.get("id") or result.get("url") or ""))
                summary["published"] += 1
                log.info("published %s on %s", post["id"], post["platform"])
            else:
                err = str(result.get("error", "unknown error"))[:300]
                attempts = post["attempts"] + 1
                if attempts >= MAX_ATTEMPTS:
                    _mark(conn, post["id"], "failed", error=err)
                    summary["failed"] += 1
                    log.warning("post %s failed permanently: %s", post["id"], err)
                else:
                    _mark(conn, post["id"], "scheduled", error=err,
                          attempts=attempts)
                    summary["retrying"] += 1
                    log.info("post %s failed (%s), retry %d/%d",
                             post["id"], err, attempts, MAX_ATTEMPTS)
            summary["details"].append({"id": post["id"],
                                       "platform": post["platform"],
                                       "ok": bool(result.get("ok"))})
    finally:
        conn.close()
    return summary


def audit_stats() -> dict:
    """Report the size of the append-only audit log.

    Nothing is ever deleted: the audit trail is append-only by design and
    the database trigger rejects updates and deletes. This only reports
    what is actually on disk.
    """
    from empire.security.audit import audit_log
    try:
        path = audit_log().path
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not path.exists():
        return {"ok": True, "path": str(path), "entries": 0, "bytes": 0}
    entries = 0
    size = 0
    try:
        with path.open("rb") as fh:
            for line in fh:
                size += len(line)
                if line.strip():
                    entries += 1
    except OSError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "path": str(path), "entries": entries, "bytes": size}


async def run_forever(interval: float, once: bool = False) -> int:
    tick = 0
    while True:
        tick += 1
        try:
            summary = await process_due_posts()
            if summary["checked"]:
                log.info("worker tick %d: %s", tick, json.dumps(summary["details"]))
            stats = audit_stats()
            if not stats.get("ok"):
                log.warning("audit check failed: %s", stats.get("error"))
        except Exception as e:                   # noqa: BLE001
            log.exception("worker tick %d failed: %s", tick, e)
        if once:
            return 0
        await asyncio.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Empire background worker")
    ap.add_argument("--interval", type=float,
                    default=float(os.getenv("EMPIRE_WORKER_INTERVAL", "30")))
    ap.add_argument("--once", action="store_true",
                    help="process the queue once and exit")
    args = ap.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s")
    log.info("worker starting (interval=%ss, queue=%s)",
             args.interval, QUEUE_DB)
    return asyncio.run(run_forever(args.interval, once=args.once))


if __name__ == "__main__":
    sys.exit(main())
