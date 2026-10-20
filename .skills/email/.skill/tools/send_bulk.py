"""send_bulk — send bulk emails with personalization."""
import asyncio
from typing import Optional
import importlib, os
# Load sibling tool module by path (skills load files, not packages)
_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "skill_email_send_email", os.path.join(_here, "send_email.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
send_email = _mod.send_email


async def send_bulk(
    template_id: str,
    recipients: list[dict],
    variables: Optional[dict] = None,
    rate_limit_per_minute: int = 50,
) -> dict:
    """Send the same email to many recipients with personal variables.

    Args:
        template_id: which template to use
        recipients: list of {"email": str, "vars": dict}
        rate_limit_per_minute: throttle to this rate

    Returns:
        dict with sent/failed counts
    """
    delay = 60.0 / rate_limit_per_minute
    sent, failed = 0, []

    for i, recipient in enumerate(recipients):
        try:
            # In real impl, load template and render with vars
            await send_email(
                to=recipient["email"],
                subject=f"[Template: {template_id}]",
                body=f"Hello {recipient.get('vars', {}).get('name', 'there')}",
            )
            sent += 1
        except Exception as e:
            failed.append({"email": recipient.get("email"), "error": str(e)})

        if i < len(recipients) - 1:
            await asyncio.sleep(delay)

    return {"sent": sent, "failed": failed, "total": len(recipients)}
