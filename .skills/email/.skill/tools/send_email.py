"""send_email tool — send an email with optional attachments."""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
import asyncio


async def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    html: bool = False,
    attachments: Optional[list[str]] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> dict:
    """Send an email via SMTP.

    Args:
        to: recipient(s) — str or list
        subject: email subject
        body: email body (plain text or HTML)
        from_email: sender (defaults to env SMTP_USER)
        html: whether body is HTML
        attachments: list of file paths to attach
        cc: CC recipients
        bcc: BCC recipients
        smtp_host: SMTP server (defaults to env SMTP_HOST)
        smtp_port: SMTP port (defaults to 587)
        smtp_user: SMTP username
        smtp_password: SMTP password

    Returns:
        dict with status and message_id
    """
    smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
    smtp_user = smtp_user or os.getenv("SMTP_USER", "")
    smtp_password = smtp_password or os.getenv("SMTP_PASSWORD", "")
    from_email = from_email or smtp_user

    if isinstance(to, str):
        to = [to]

    msg = MIMEMultipart("alternative")
    msg["From"] = from_email
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject

    if html:
        msg.attach(MIMEText(body, "html"))
    else:
        msg.attach(MIMEText(body, "plain"))

    # Attachments
    for path in attachments or []:
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(path)}",
        )
        msg.attach(part)

    recipients = to + (cc or []) + (bcc or [])

    # Send in thread pool (smtplib is blocking)
    def _send():
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, recipients, msg.as_string())
        return msg.as_string().split("\n")[0].split(": ")[-1]

    message_id = await asyncio.get_event_loop().run_in_executor(None, _send)

    return {
        "status": "sent",
        "to": to,
        "subject": subject,
        "message_id": message_id,
    }
