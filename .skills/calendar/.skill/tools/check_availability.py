"""check_availability — real availability check for a date range."""
import sys, os
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_fs = importlib.util.spec_from_file_location(
    "fs", os.path.join(os.path.dirname(os.path.abspath(__file__)), "find_slot.py"))
_fs_m = importlib.util.module_from_spec(_fs); _fs.loader.exec_module(_fs_m)


async def check_availability(date: str = None, days: int = 1,
                             duration_minutes: int = 60,
                             work_start_hour: int = 9, work_end_hour: int = 18) -> dict:
    """
    Report free/busy hours for a day.

    Args:
        date: ISO date (default: today)
        days: number of days to check
        duration_minutes: slot granularity
        work_start_hour: earliest hour
        work_end_hour: latest hour

    Returns:
        {"ok": True, "date": str, "free_hours": [...], "busy_hours": [...]}
    """
    r = await _fs_m.find_slot(days=days, duration_minutes=duration_minutes,
                              work_start_hour=work_start_hour,
                              work_end_hour=work_end_hour, max_slots=500)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error")}
    total = r["duration_minutes"] * ((work_end_hour - work_start_hour) * 60 // r["duration_minutes"])
    free = r["count"]
    return {"ok": True, "date": date or datetime.now(timezone.utc).date().isoformat(),
            "days": days, "slot_minutes": r["duration_minutes"],
            "free_slots": free, "total_slots": total * days,
            "availability_pct": round(100 * free / max(total * days, 1), 1),
            "busy_events": r.get("busy_events", 0),
            "free_hours": [s["start"] for s in r["slots"][:12]]}
