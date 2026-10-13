"""check_inbox — check IMAP inbox for new messages."""
import os
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional
import asyncio


async def check_inbox(
    folder: str = "INBOX",
    limit: int = 10,
    unread_only: bool = True,
    imap_host: Optional[str] = None,
    imap_user: Optional[str] = None,
    imap_password: Optional[str] = None,
) -> dict:
    """Check inbox for messages.

    Args:
        folder: IMAP folder
        limit: max number of messages
        unread_only: only return unread
        imap_host: defaults to env IMAP_HOST
        imap_user: defaults to env IMAP_USER
        imap_password: defaults to env IMAP_PASSWORD

    Returns:
        dict with messages list
    """
    imap_host = imap_host or os.getenv("IMAP_HOST", "imap.gmail.com")
    imap_user = imap_user or os.getenv("IMAP_USER", "")
    imap_password = imap_password or os.getenv("IMAP_PASSWORD", "")

    def _fetch():
        with imaplib.IMAP4_SSL(imap_host) as imap:
            imap.login(imap_user, imap_password)
            imap.select(folder)
            criteria = "UNSEEN" if unread_only else "ALL"
            _, data = imap.search(None, criteria)
            ids = data[0].split()[-limit:]
            messages = []
            for msg_id in ids:
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8")
                from_, encoding = decode_header(msg.get("From", ""))[0]
                if isinstance(from_, bytes):
                    from_ = from_.decode(encoding or "utf-8")
                messages.append({
                    "id": msg_id.decode(),
                    "subject": subject,
                    "from": from_,
                    "date": str(parsedate_to_datetime(msg["Date"])) if msg["Date"] else None,
                })
            return messages

    messages = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return {"messages": messages, "count": len(messages)}
