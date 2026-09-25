"""
Audit logging — every privileged action is logged for compliance.

Writes JSON-lines to /var/log/ai-empire/audit.log (or Redis stream).
Format:
  {"ts": "...", "tenant": "...", "actor": "...", "role": "...",
   "action": "send_outreach", "target": "...", "ok": true,
   "args": {...}, "result_summary": "..."}

In production, pipe this to an immutable store (e.g., Loki + WORM S3,
or AWS CloudWatch Logs with retention lock).

Also increments Prometheus metrics (empire_audit_actions_total, empire_pii_redactions_total)
when the metrics module is available.
"""
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .auth import AuthContext
from .pii import redact as redact_pii

# Optional metrics — wire up if orchestrator is on the path
try:
    from orchestrator.metrics import metrics
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False


@dataclass
class AuditEntry:
    ts: str
    request_id: str
    tenant: str
    actor: str
    role: str
    action: str
    target: str = ""
    ok: bool = True
    error: str = ""
    args: dict = field(default_factory=dict)
    result_summary: str = ""
    ip: str = ""
    user_agent: str = ""


class AuditLogger:
    """
    Append-only audit logger. Writes JSON lines to file (and optionally stdout).

    Enable via PII_AUDIT_LOG=true (default).
    """
    def __init__(self, path: str = "/var/log/ai-empire/audit.log",
                 also_stderr: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.also_stderr = also_stderr
        self.enabled = os.getenv("PII_AUDIT_LOG", "true").lower() in ("1", "true", "yes")
        # Standard logger for stderr path
        self._log = logging.getLogger("ai-empire.audit")
        self._log.setLevel(logging.INFO)
        if also_stderr and not self._log.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(logging.Formatter("%(message)s"))
            self._log.addHandler(h)

    def log(self, auth: AuthContext, action: str,
            target: str = "", args: dict | None = None,
            ok: bool = True, error: str = "",
            result_summary: str = "", request_id: str = "",
            ip: str = "", user_agent: str = "") -> None:
        if not self.enabled:
            return
        scrubbed_args = _scrub(args or {})
        scrubbed_summary = redact_pii(result_summary)[:500]
        entry = AuditEntry(
            ts=datetime.now(timezone.utc).isoformat(),
            request_id=request_id or str(uuid.uuid4()),
            tenant=auth.tenant,
            actor=auth.sub,
            role=auth.role.value,
            action=action,
            target=target,
            ok=ok,
            error=error,
            args=scrubbed_args,
            result_summary=scrubbed_summary,
            ip=ip,
            user_agent=user_agent[:200],
        )
        line = json.dumps(asdict(entry), default=str, ensure_ascii=False)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # file may be read-only; that's ok, we still log to stderr
        if self.also_stderr:
            self._log.info(line)

        # Prometheus metrics
        if _HAS_METRICS:
            try:
                metrics.audit_actions.inc(
                    tenant=auth.tenant, actor=auth.sub, action=action,
                )
                # Count each PII pattern that was redacted
                if result_summary:
                    from .pii import _PATTERNS as _P
                    for name, p in _P.items():
                        if p.regex.search(result_summary):
                            metrics.pii_redactions.inc(amount=1.0, pattern=name, action=action)
            except Exception:
                pass


def _scrub(obj: Any) -> Any:
    """Recursively redact PII from any dict/list structure."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if k.lower() not in {"password", "secret", "api_key", "token"}}
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, str):
        return redact_pii(obj)
    return obj


_default: Optional[AuditLogger] = None


def audit_log() -> AuditLogger:
    global _default
    if _default is None:
        _default = AuditLogger()
    return _default
