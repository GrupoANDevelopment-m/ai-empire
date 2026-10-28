"""find_slot — real free/busy computation."""
import sys, os
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_le = importlib.util.spec_from_file_location(
    "le", os.path.join(os.path.dirname(os.path.abspath(__file__)), "list_events.py"))
_le_m = importlib.util.module_from_spec(_le); _le.loader.exec_module(_le_m)
from _cal import call, backend


async def find_slot(days: int = 14, duration_minutes: int = 30,
                    work_start_hour: int = 9, work_end_hour: int = 18,
                    timezone_name: str = "UTC", max_slots: int = 10) -> dict:
    """
    Find free time slots in the next N days within working hours.

    Args:
        days: search window
        duration_minutes: slot length
        work_start_hour: earliest hour (0-23)
        work_end_hour: latest hour (0-23)
        timezone_name: IANA timezone
        max_slots: how many slots to return

    Returns:
        {"ok": True, "slots": [{"start","end"}], "count": int}
    """
    if not (0 <= work_start_hour < work_end_hour <= 24):
        raise ValueError("invalid work hours")
    if duration_minutes < 5:
        raise ValueError("duration must be >= 5 minutes")

    ev = await _le_m.list_events(days=days, max_results=250)
    if not ev.get("ok"):
        return {"ok": False, "error": ev.get("error"), "slots": []}

    def parse(s):
        if not s: return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    busy = []
    for e in ev["events"]:
        s, en = parse(e.get("start")), parse(e.get("end"))
        if s and en and en > s:
            busy.append((s, en))

    slots, now = [], datetime.now(timezone.utc).replace(second=0, microsecond=0)
    day = now
    for _ in range(days):
        cur = day.replace(hour=work_start_hour, minute=0)
        day_end = day.replace(hour=work_end_hour, minute=0)
        while cur + timedelta(minutes=duration_minutes) <= day_end:
            fin = cur + timedelta(minutes=duration_minutes)
            if not any(cur < b and fin > a for a, b in busy):
                if cur > now:
                    slots.append({"start": cur.isoformat(), "end": fin.isoformat()})
                if len(slots) >= max_slots:
                    break
            cur = fin
        if len(slots) >= max_slots:
            break
        day = (day + timedelta(days=1)).replace(hour=0, minute=0)

    return {"ok": True, "count": len(slots), "duration_minutes": duration_minutes,
            "busy_events": len(busy), "slots": slots, "backend": backend()}
