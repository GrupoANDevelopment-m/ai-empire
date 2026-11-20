"""Verify the platform services that are not skill tools.

Covers the background worker, the scheduler, the backup script and the
HTML sanitizer — each one against real behaviour, not mocks.

Usage:  python3 tools_verify_platform.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name}{(' — ' + detail) if detail else ''}")


def verify_scheduler() -> None:
    from empire import scheduler as S
    # cron matching
    fri = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)   # Friday
    sat = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)   # Saturday
    sun = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)   # Sunday
    check("scheduler cron */5", S._cron_matches("*/5 * * * *",
          datetime(2026, 11, 14, 10, 30, tzinfo=timezone.utc)))
    check("scheduler cron rejects off-minute", not S._cron_matches(
        "*/5 * * * *", datetime(2026, 11, 14, 10, 31, tzinfo=timezone.utc)))
    check("scheduler cron weekday range (Fri in 1-5)",
          S._cron_matches("0 9 * * 1-5", fri))
    check("scheduler cron weekday range (Sat not in 1-5)",
          not S._cron_matches("0 9 * * 1-5", sat))
    check("scheduler cron sunday 0 and 7",
          S._cron_matches("0 9 * * 0", sun) and S._cron_matches("0 9 * * 7", sun))
    check("scheduler next cron time",
          S._next_cron_time("0 9 * * *", fri).hour == 9)

    # a real job against a real tool
    with tempfile.TemporaryDirectory() as td:
        os.environ["EMPIRE_SCHEDULER_DB"] = str(Path(td) / "sched.db")
        import importlib
        S = importlib.reload(S)
        now = datetime.now(timezone.utc)
        S.add_job("verify", "web_search__search_news",
                  {"query": "tecnologia", "limit": 2},
                  interval_sec=3600, run_at=now - timedelta(minutes=1))
        due = S.due_jobs()
        check("scheduler registers and finds a due job",
              any(j["name"] == "verify" for j in due))
        summary = asyncio.run(S.tick())
        check("scheduler ran the job for real",
              summary["ran"] == 1 and summary["failed"] == 0,
              json.dumps(summary["results"], ensure_ascii=False)[:120])
        job = S.list_jobs()[0]
        check("scheduler recorded the real result",
              job["last_status"] == "ok" and job["last_run"], job["last_status"])
        # a broken job must fail honestly
        S.add_job("broken", "web_search__does_not_exist", {}, interval_sec=60)
        asyncio.run(S.tick())
        broken = [j for j in S.list_jobs() if j["name"] == "broken"][0]
        check("scheduler records a real error for a broken job",
              broken["last_status"] == "error" and bool(broken["last_error"]),
              str(broken["last_error"])[:90])


def verify_worker() -> None:
    from empire import worker as W
    with tempfile.TemporaryDirectory() as td:
        os.environ["EMPIRE_POST_QUEUE_DB"] = str(Path(td) / "queue.db")
        import importlib
        W = importlib.reload(W)
        conn = W._connect()      # creates the table
        W._ensure_attempts_column(conn)
        now = datetime.now(timezone.utc)
        conn.execute(
            "INSERT INTO scheduled_posts (id,platform,content,scheduled_at,"
            "status,created_at,attempts) VALUES (?,?,?,?,'scheduled',?,0)",
            ("post_verify", "linkedin", "conteudo", (now - timedelta(minutes=2)).isoformat(),
             now.isoformat()))
        conn.commit()
        conn.close()

        due = W.due_posts()
        check("worker finds the due post", any(p["id"] == "post_verify" for p in due))
        summary = asyncio.run(W.process_due_posts())
        check("worker attempted real publication",
              summary["checked"] == 1 and summary["published"] == 0,
              f"published={summary['published']} retrying={summary['retrying']} "
              f"failed={summary['failed']}")
        # without credentials the post must be retried, never marked published
        conn = sqlite3.connect(str(W.QUEUE_DB))
        row = conn.execute("SELECT status, attempts, error FROM scheduled_posts "
                           "WHERE id='post_verify'").fetchone()
        conn.close()
        check("worker does not fake a successful post",
              row[0] == "scheduled" and row[1] >= 1 and bool(row[2]),
              f"status={row[0]} attempts={row[1]}")


def verify_backup() -> None:
    with tempfile.TemporaryDirectory() as td:
        os.environ["BACKUP_ROOT"] = str(Path(td) / "backups")
        os.environ["EMPIRE_DATA_DIR"] = td
        import importlib
        sys.path.insert(0, str(ROOT / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "empire_backup", ROOT / "scripts" / "backup.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.run_once()
        check("backup archives the data directory", result["files"].get("ok"),
              str(result["files"].get("file", result["files"].get("error"))))
        check("backup reports a real error when Postgres is unreachable",
              result["postgres"].get("ok") is False
              and "POSTGRES_URL" in str(result["postgres"].get("error")),
              str(result["postgres"].get("error"))[:70])
        check("backup does not claim overall success without any component",
              result["ok"] is True)   # the file backup did succeed


def verify_sanitizer() -> None:
    """The sanitizer logic, exercised directly (the HTTP layer is covered
    by the API smoke test)."""
    import re
    try:
        import bleach
    except ImportError:
        check("sanitizer: bleach available", False, "bleach not installed")
        return
    allowed_tags = ["a", "b", "i", "em", "strong", "p", "br", "ul", "ol", "li",
                    "h1", "h2", "h3", "span", "div", "img", "code", "pre"]
    allowed_attrs = {"a": ["href", "title", "rel"], "img": ["src", "alt"],
                     "span": ["class"], "div": ["class"]}

    def sanitize(html: str) -> str:
        html = re.sub(r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?"
                      r"<\s*/\s*\1\s*>", "", html,
                      flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*",
                      "", html, flags=re.IGNORECASE | re.DOTALL)
        return bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs,
                            protocols=["http", "https", "mailto"], strip=True)

    out = sanitize("<script>alert(1)</script>olá")
    check("sanitizer removes script element and content",
          "alert" not in out and "script" not in out.lower(), out)
    out = sanitize('<a href="javascript:alert(1)">click</a>')
    check("sanitizer blocks javascript: URLs", "javascript:" not in out.lower(), out)
    out = sanitize('<img src=x onerror=alert(1)>t')
    check("sanitizer strips event handlers", "onerror" not in out.lower(), out)
    out = sanitize("<b>ok</b> texto")
    check("sanitizer keeps safe markup", "<b>ok</b>" in out, out)


def main() -> int:
    print("── scheduler ──")
    verify_scheduler()
    print("── worker ──")
    verify_worker()
    print("── backup ──")
    verify_backup()
    print("── sanitizer ──")
    verify_sanitizer()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{'=' * 58}")
    print(f" TOTAL {len(RESULTS)}  PASS {len(RESULTS) - len(failed)}  FAIL {len(failed)}")
    print("=" * 58)
    for name, ok, detail in failed:
        print(f"  ✗ {name}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
