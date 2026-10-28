"""send_bulk — send a templated email to many recipients, real SMTP."""
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional
import importlib

_TD = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "email_send_email_mod", os.path.join(_TD, "send_email.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
send_email = _mod.send_email

def _find_template_dir() -> Path:
    """Locate the template store.

    The tool may live at <skill>/tools/ or <skill>/.skill/tools/, so the
    template folder is searched at every plausible level.
    """
    env = os.getenv("EMPIRE_EMAIL_TEMPLATES")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "templates"
        if cand.is_dir() and any(cand.glob("*.json")):
            return cand
    return here.parent.parent / "templates"


TEMPLATE_DIR = _find_template_dir()

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def list_templates() -> list:
    """Return the available template ids."""
    if not TEMPLATE_DIR.is_dir():
        return []
    out = []
    for f in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": d.get("id", f.stem),
                    "subject": d.get("subject", ""),
                    "required_vars": d.get("required_vars", [])})
    return out


def load_template(template_id: str) -> dict:
    """Load a template by id from the template store."""
    if not template_id or not str(template_id).strip():
        raise ValueError("template_id is required")
    path = TEMPLATE_DIR / f"{template_id}.json"
    if not path.is_file():
        available = ", ".join(t["id"] for t in list_templates()) or "(none)"
        raise FileNotFoundError(
            f"template {template_id!r} not found at {path}. Available: {available}")
    data = json.loads(path.read_text(encoding="utf-8"))
    for field in ("subject", "body"):
        if not data.get(field):
            raise ValueError(f"template {template_id!r} has no {field}")
    return data


def render(text: str, variables: dict) -> str:
    """Substitute {{var}} placeholders. Unknown vars are left visible so a
    mistake is obvious rather than silently producing empty copy."""
    def repl(m):
        key = m.group(1)
        val = variables
        for part in key.split("."):
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return m.group(0)
        return str(val)
    return _VAR_RE.sub(repl, text)


async def send_bulk(
    template_id: str,
    recipients: list[dict],
    variables: Optional[dict] = None,
    rate_limit_per_minute: int = 50,
) -> dict:
    """Send the same templated email to many recipients with personal variables.

    Args:
        template_id: template to use (see .skills/email/templates/*.json)
        recipients: list of {"email": str, "vars": dict}
        variables: base variables shared by every recipient
        rate_limit_per_minute: throttle to this rate

    Returns:
        {"ok": bool, "sent": int, "failed": [...], "total": int}
    """
    if not recipients:
        raise ValueError("recipients cannot be empty")
    if not isinstance(recipients, list):
        raise ValueError("recipients must be a list")
    if rate_limit_per_minute <= 0:
        raise ValueError("rate_limit_per_minute must be positive")

    tpl = load_template(template_id)
    base_vars = dict(variables or {})
    required = tpl.get("required_vars", [])

    delay = 60.0 / rate_limit_per_minute
    sent, failed = 0, []

    for i, recipient in enumerate(recipients):
        if not isinstance(recipient, dict) or not recipient.get("email"):
            failed.append({"email": recipient.get("email") if isinstance(recipient, dict) else None,
                           "error": "recipient has no 'email' field"})
            continue
        rvars = {**base_vars, **(recipient.get("vars") or {})}
        missing = [v for v in required if v not in rvars]
        if missing:
            failed.append({"email": recipient["email"],
                           "error": f"missing template variables: {', '.join(missing)}"})
            continue
        try:
            await send_email(
                to=recipient["email"],
                subject=render(tpl["subject"], rvars),
                body=render(tpl["body"], rvars),
            )
            sent += 1
        except Exception as e:
            failed.append({"email": recipient.get("email"), "error": str(e)[:200]})

        if i < len(recipients) - 1:
            await asyncio.sleep(delay)

    return {"ok": sent > 0, "sent": sent, "failed": failed,
            "total": len(recipients), "template_id": template_id}
