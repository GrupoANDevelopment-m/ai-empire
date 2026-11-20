"""Empire Scheduler — real cron-style scheduler.

Runs recurring jobs on a schedule. Jobs are stored in a SQLite database
(the same pattern the social-media queue uses), each one describing:

    name          unique identifier
    tool          the namespaced skill tool to run, e.g. "web_search__search_news"
    args          JSON object with the tool arguments
    interval_sec  seconds between runs (or "cron": "m h * * *" for a
                  five-field cron expression)
    enabled       1/0
    last_run      ISO timestamp of the last attempt
    next_run      ISO timestamp of the next attempt
    last_status   "ok" | "error" | "skipped"
    last_error    the real error message from the last failed run

Every run calls the real tool and records the real result. A failing job
is retried on the next tick with its actual error message; nothing is
silently swallowed.

Usage:
    python3 -m empire.scheduler --list
    python3 -m empire.scheduler --add news '{"query":"AI"}' --every 3600
    python3 -m empire.scheduler --once
    python3 -m empire.scheduler
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "empire").is_dir() and (p / ".skills").is_dir())

log = logging.getLogger("empire.scheduler")

SCHED_DB = Path(os.getenv("EMPIRE_SCHEDULER_DB",
                           f"{_ROOT}/data/scheduler.db"))
TICK_SECONDS = float(os.getenv("EMPIRE_SCHEDULER_TICK", "30"))


def _connect() -> sqlite3.Connection:
    SCHED_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SCHED_DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        name TEXT PRIMARY KEY,
        tool TEXT NOT NULL,
        args TEXT NOT NULL DEFAULT '{}',
        interval_sec INTEGER,
        cron TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        last_run TEXT,
        next_run TEXT,
        last_status TEXT,
        last_error TEXT,
        created_at TEXT NOT NULL)""")
    conn.commit()
    return conn


# ─── cron ────────────────────────────────────────────────────────────────────
def _field_matches(spec: str, value: int, low: int, high: int) -> bool:
    """Match one cron field against a value.

    Supports ``*``, ``*/n``, ``a-b``, ``a,b`` and plain numbers.
    """
    if spec.strip() == "*":
        return True
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, _, step_s = part.partition("/")
            step = int(step_s)
            if step <= 0:
                raise ValueError(f"invalid cron step: {step_s}")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def _dow_matches(spec: str, when: datetime) -> bool:
    """Day-of-week match, accepting 0 and 7 for Sunday as cron does."""
    cron_dow = (when.weekday() + 1) % 7          # 0=Sunday .. 6=Saturday
    parts = []
    for part in spec.split(","):
        part = part.strip()
        if part == "7":
            part = "0"
        elif "-" in part:
            a, _, b = part.partition("-")
            if b == "7":
                part = f"{a}-6"
        parts.append(part)
    return _field_matches(",".join(parts), cron_dow, 0, 6)


def _cron_matches(expr: str, when: datetime) -> bool:
    """Whether a five-field cron expression matches the given minute.

    Fields: minute hour day-of-month month day-of-week.
    Supports *, */n, a-b, a,b and numbers. Day-of-week 0 and 7 are Sunday.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron expression needs 5 fields, got {len(fields)}")
    minute, hour, dom, month, dow = fields

    return (_field_matches(minute, when.minute, 0, 59)
            and _field_matches(hour, when.hour, 0, 23)
            and _field_matches(dom, when.day, 1, 31)
            and _field_matches(month, when.month, 1, 12)
            and _dow_matches(dow, when))


def _next_cron_time(expr: str, after: datetime) -> datetime:
    """Next minute at or after `after` that matches the cron expression."""
    when = after.replace(second=0, microsecond=0)
    if when < after:
        when += timedelta(minutes=1)
    for _ in range(60 * 24 * 366):        # search up to a year
        if _cron_matches(expr, when):
            return when
        when += timedelta(minutes=1)
    raise ValueError(f"cron expression never matches: {expr!r}")


# ─── job store ───────────────────────────────────────────────────────────────
def add_job(name: str, tool: str, args: dict | None = None,
            interval_sec: int | None = None, cron: str | None = None,
            run_at: datetime | None = None) -> dict:
    """Register a job. Exactly one of interval_sec / cron must be given."""
    if not name.strip():
        raise ValueError("name is required")
    if not tool.strip():
        raise ValueError("tool is required")
    if (interval_sec is None) == (cron is None):
        raise ValueError("give exactly one of interval_sec or cron")
    if cron:
        _cron_matches(cron, datetime.now(timezone.utc))   # validate now
    now = datetime.now(timezone.utc)
    next_run = run_at or (now if interval_sec else _next_cron_time(cron, now))
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO jobs "
            "(name,tool,args,interval_sec,cron,enabled,next_run,created_at) "
            "VALUES (?,?,?,?,?,1,?,?)",
            (name, tool, json.dumps(args or {}), interval_sec, cron,
             next_run.isoformat(), now.isoformat()))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name, "tool": tool,
            "interval_sec": interval_sec, "cron": cron,
            "next_run": next_run.isoformat()}


def list_jobs() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name,tool,args,interval_sec,cron,enabled,last_run,"
            "next_run,last_status,last_error FROM jobs ORDER BY name"
        ).fetchall()
        return [{"name": r[0], "tool": r[1], "args": json.loads(r[2] or "{}"),
                 "interval_sec": r[3], "cron": r[4], "enabled": bool(r[5]),
                 "last_run": r[6], "next_run": r[7], "last_status": r[8],
                 "last_error": r[9]} for r in rows]
    finally:
        conn.close()


def due_jobs(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    return [j for j in list_jobs()
            if j["enabled"] and j["next_run"] and j["next_run"] <= now.isoformat()]


def _record(conn: sqlite3.Connection, job: dict, status: str, error: str,
            next_run: datetime) -> None:
    conn.execute(
        "UPDATE jobs SET last_run=?, next_run=?, last_status=?, last_error=? "
        "WHERE name=?",
        (datetime.now(timezone.utc).isoformat(), next_run.isoformat(),
         status, error[:500] or None, job["name"]))
    conn.commit()


async def run_job(job: dict) -> dict:
    """Execute one job through the real tool registry."""
    from empire.agent.llm.tools import execute_tool
    try:
        raw = await execute_tool(job["tool"], job["args"])
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        return {"ok": False, "error": f"tool returned non-JSON: {str(raw)[:200]}"}
    if isinstance(result, dict) and result.get("ok") is False:
        return {"ok": False, "error": str(result.get("error", "tool failed"))[:400]}
    return {"ok": True, "result": result}


async def tick(now: datetime | None = None) -> dict:
    """Run every job that is due. Returns a real summary."""
    now = now or datetime.now(timezone.utc)
    jobs = due_jobs(now)
    summary = {"checked": len(jobs), "ran": 0, "failed": 0, "results": []}
    if not jobs:
        return summary
    conn = _connect()
    try:
        for job in jobs:
            outcome = await run_job(job)
            if job["cron"]:
                nxt = _next_cron_time(job["cron"], now)
            else:
                nxt = now + timedelta(seconds=int(job["interval_sec"] or 60))
            if outcome["ok"]:
                _record(conn, job, "ok", "", nxt)
                summary["ran"] += 1
            else:
                _record(conn, job, "error", outcome.get("error", ""), nxt)
                summary["failed"] += 1
                log.warning("job %s failed: %s", job["name"],
                            outcome.get("error"))
            summary["results"].append({"name": job["name"],
                                       "ok": outcome["ok"],
                                       "error": outcome.get("error")})
    finally:
        conn.close()
    return summary


async def run_forever(once: bool = False) -> int:
    while True:
        try:
            summary = await tick()
            if summary["checked"]:
                log.info("scheduler tick: %s",
                         json.dumps(summary["results"], ensure_ascii=False))
        except Exception as e:                   # noqa: BLE001
            log.exception("scheduler tick failed: %s", e)
        if once:
            return 0
        await asyncio.sleep(TICK_SECONDS)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Empire scheduler")
    ap.add_argument("--list", action="store_true", help="list jobs and exit")
    ap.add_argument("--add", metavar="NAME", help="register a job")
    ap.add_argument("--tool", default="", help="namespaced tool to run")
    ap.add_argument("--args", default="{}", help="JSON arguments for the tool")
    ap.add_argument("--every", type=int, help="run every N seconds")
    ap.add_argument("--cron", help="five-field cron expression")
    ap.add_argument("--once", action="store_true",
                    help="run due jobs once and exit")
    args = ap.parse_args()

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s")

    if args.list:
        jobs = list_jobs()
        if not jobs:
            print("no jobs registered")
        for j in jobs:
            print(f"  {j['name']:24s} {j['tool']:36s} "
                  f"next={j['next_run']} status={j['last_status']}")
        return 0

    if args.add:
        if not args.tool:
            ap.error("--add requires --tool")
        payload = json.loads(args.args)
        if args.every is None and not args.cron:
            ap.error("--add requires --every or --cron")
        info = add_job(args.add, args.tool, payload,
                       interval_sec=args.every, cron=args.cron)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    log.info("scheduler starting (tick=%ss, db=%s)", TICK_SECONDS, SCHED_DB)
    return asyncio.run(run_forever(once=args.once))


if __name__ == "__main__":
    sys.exit(main())
