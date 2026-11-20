"""Backup — real backups for the AI Empire production stack.

Performs actual work:

  * Postgres: a logical dump via ``pg_dump`` over the connection URL.
  * Filesystem: a tar.gz archive of the empire data directory.
  * Pruning: old backups are removed according to the retention policy.

Nothing is faked: if ``pg_dump`` is missing or the database is
unreachable, the backup for that component fails and the error is
reported — the script never writes an empty file and claims success.

Usage:
    python3 scripts/backup.py --once          # back up now and exit
    python3 scripts/backup.py --cron          # loop, every --interval hours
    python3 scripts/backup.py --cron --interval 6
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = Path(os.getenv("BACKUP_ROOT", "/var/backups/ai-empire"))
DATA_DIR = Path(os.getenv("EMPIRE_DATA_DIR", str(ROOT / "data")))
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
POSTGRES_URL = os.getenv("POSTGRES_URL", "")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_postgres(ts: str) -> dict:
    """Logical dump of Postgres via pg_dump."""
    if not POSTGRES_URL:
        return {"ok": False, "error": "POSTGRES_URL is not set"}
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        return {"ok": False, "error": "pg_dump binary not found in PATH"}
    out = BACKUP_ROOT / f"postgres-{ts}.sql.gz"
    try:
        proc = subprocess.run(
            [pg_dump, "--dbname", POSTGRES_URL, "--clean", "--if-exists"],
            capture_output=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pg_dump timed out after 30 minutes"}
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:300]
        return {"ok": False, "error": f"pg_dump failed: {err}"}
    with gzip.open(out, "wb") as fh:
        fh.write(proc.stdout)
    return {"ok": True, "file": str(out), "bytes": out.stat().st_size}


def backup_files(ts: str) -> dict:
    """Archive the empire data directory."""
    if not DATA_DIR.exists():
        return {"ok": False, "error": f"data directory not found: {DATA_DIR}"}
    out = BACKUP_ROOT / f"data-{ts}.tar.gz"
    try:
        with tarfile.open(out, "w:gz") as tar:
            tar.add(DATA_DIR, arcname=DATA_DIR.name)
    except (OSError, tarfile.TarError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "file": str(out), "bytes": out.stat().st_size}


def prune(days: int = RETENTION_DAYS) -> dict:
    """Remove backups older than the retention window."""
    if not BACKUP_ROOT.exists():
        return {"ok": True, "removed": 0, "note": "no backup root yet"}
    cutoff = time.time() - days * 86400
    removed = []
    for f in BACKUP_ROOT.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("LATEST"):
            continue
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed.append(f.name)
        except OSError:
            continue
    return {"ok": True, "removed": len(removed), "files": removed}


def run_once() -> dict:
    ts = _ts()
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    results = {"timestamp": ts, "root": str(BACKUP_ROOT),
               "postgres": backup_postgres(ts), "files": backup_files(ts),
               "prune": prune()}
    latest = BACKUP_ROOT / "LATEST"
    try:
        latest.mkdir(exist_ok=True)
        for key, res in (("postgres", results["postgres"]),
                         ("files", results["files"])):
            if res.get("ok"):
                target = latest / Path(res["file"]).name
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(res["file"])
    except OSError as e:
        results["latest_error"] = f"{type(e).__name__}: {e}"
    results["ok"] = any(r.get("ok") for r in
                         (results["postgres"], results["files"]))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Empire backup")
    ap.add_argument("--once", action="store_true", help="run one backup and exit")
    ap.add_argument("--cron", action="store_true",
                    help="run in a loop, backing up every --interval hours")
    ap.add_argument("--interval", type=float,
                    default=float(os.getenv("BACKUP_INTERVAL_HOURS", "24")))
    args = ap.parse_args()

    if not (args.once or args.cron):
        args.once = True

    while True:
        result = run_once()
        for key in ("postgres", "files", "prune"):
            r = result[key]
            status = "✓" if r.get("ok") else "✗"
            detail = r.get("file") or r.get("error") or ""
            print(f"[{result['timestamp']}] {status} {key}: {detail}")
        if args.once:
            return 0 if result["ok"] else 1
        time.sleep(args.interval * 3600)


if __name__ == "__main__":
    sys.exit(main())
