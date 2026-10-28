"""send_invite — send an ICS calendar invite by email."""
import sys, os, uuid, hashlib
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
_bm = importlib.util.spec_from_file_location(
    "si_bm", os.path.join(os.path.dirname(os.path.abspath(__file__)), "book_meeting.py"))
_bm_m = importlib.util.module_from_spec(_bm); _bm.loader.exec_module(_bm_m)


def _ics_escape(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\n", "\\n"))


async def send_invite(title: str, attendees: list, start: str,
                      duration_minutes: int = 60, description: str = "",
                      organizer: str = None, location: str = "") -> dict:
    """
    Generate an RFC-5545 .ics file and email it via SMTP.

    Args:
        title: event title
        attendees: list of emails
        start: ISO start datetime
        duration_minutes: length
        description: agenda
        organizer: organizer email (from SMTP_USER if omitted)
        location: location string

    Returns:
        {"ok": True, "ics_path": str, "sent_to": [...], "method": str}
    """
    import smtplib, ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.application import MIMEApplication

    if not attendees:
        raise ValueError("attendees required")
    s = datetime.fromisoformat(start.replace("Z", "+00:00"))
    e = s + timedelta(minutes=duration_minutes)
    uid = f"{uuid.uuid4()}@ai-empire"
    dt = lambda d: d.strftime("%Y%m%dT%H%M%SZ")

    ics = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//AI Empire//EN",
        "CALSCALE:GREGORIAN", "METHOD:REQUEST",
        "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{dt(datetime.utcnow())}",
        f"DTSTART:{dt(s)}", f"DTEND:{dt(e)}",
        f"SUMMARY:{_ics_escape(title)}",
        f"DESCRIPTION:{_ics_escape(description)}",
        f"LOCATION:{_ics_escape(location)}",
        f"ORGANIZER;CN=AI Empire:mailto:{organizer or os.getenv('SMTP_USER','noreply@empire.local')}",
        *[f"ATTENDEE;RSVP=TRUE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION:mailto:{a}"
          for a in attendees],
        "STATUS:CONFIRMED", "SEQUENCE:0", "BEGIN:VALARM", "TRIGGER:-PT15M",
        "ACTION:DISPLAY", "DESCRIPTION:Reminder", "END:VALARM", "END:VEVENT",
        "END:VCALENDAR"])

    ics_path = f"/tmp/invite_{hashlib.md5(uid.encode()).hexdigest()[:8]}.ics"
    open(ics_path, "w", newline="").write(ics)

    host = os.getenv("SMTP_HOST", "")
    user = os.getenv("SMTP_USER", "")
    pw = os.getenv("SMTP_PASSWORD", "")
    if not (host and user and pw):
        return {"ok": True, "ics_path": ics_path, "sent_to": [], "method": "ics-only",
                "note": "SMTP not configured (.env: SMTP_HOST/SMTP_USER/SMTP_PASSWORD) — "
                        "ICS written to disk, not emailed"}

    msg = MIMEMultipart("alternative")
    msg["From"] = organizer or user
    msg["To"] = ", ".join(attendees)
    msg["Subject"] = f"Convite: {title}"
    msg.attach(MIMEText(description or title, "plain"))
    cal = MIMEApplication(ics.encode(), "calendar", method="REQUEST")
    cal.add_header("Content-Disposition", "attachment; filename=invite.ics")
    msg.attach(cal)

    import asyncio
    def _send():
        with smtplib.SMTP_SSL(host, 465, context=ssl.create_default_context()) as srv:
            srv.login(user, pw); srv.send_message(msg)
    await asyncio.get_event_loop().run_in_executor(None, _send)
    return {"ok": True, "ics_path": ics_path, "sent_to": attendees,
            "method": "smtp+ics", "uid": uid}
