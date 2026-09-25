"""
Tenant isolation — enforce that every tool call only touches data owned
by the requesting tenant.

Plumbing:
  JWT carries `tenant` claim (set on issue_token)
  AuthContext.tenant is propagated into EmpireAgent
  Every tool call filters by tenant_id
  Every Postgres query has WHERE tenant = $tenant
  Every Redis key is prefixed by tenant
  Every filesystem path includes tenant_id

This is the Gate 0 item that closes the audit-log gap.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Optional

log = logging.getLogger("empire.tenant")

# ContextVar so async tasks inherit the right tenant without explicit passing
_current_tenant: ContextVar[str] = ContextVar("current_tenant", default="default")


def set_current_tenant(tenant: str) -> None:
    """Called by the agent loop per-request. Empty string is invalid."""
    if not tenant or not isinstance(tenant, str):
        raise ValueError(f"tenant must be non-empty string, got {tenant!r}")
    tenant = tenant.strip().lower()
    if not tenant.replace("-", "").replace("_", "").isalnum():
        raise ValueError(f"tenant must be alphanumeric/dash/underscore: {tenant!r}")
    if len(tenant) > 64:
        raise ValueError(f"tenant name too long (max 64 chars): {tenant!r}")
    _current_tenant.set(tenant)


def get_current_tenant() -> str:
    return _current_tenant.get()


def tenant_key(suffix: str) -> str:
    """Build a tenant-prefixed key for Redis, file paths, etc."""
    t = get_current_tenant()
    return f"t:{t}:{suffix}"


def tenant_filter_clause(column: str = "tenant") -> tuple[str, list[Any]]:
    """Return (WHERE clause, params) for SQL queries. Always applied."""
    t = get_current_tenant()
    return (f"{column} = %s", [t])


def assert_tenant_match(lead_or_session: dict, key: str = "tenant") -> None:
    """Raise if a fetched record belongs to another tenant."""
    record_tenant = lead_or_session.get(key)
    if record_tenant != get_current_tenant():
        log.error(
            "tenant.violation: expected=%s got=%s resource=%s",
            get_current_tenant(), record_tenant, lead_or_session.get("id", "?"),
        )
        raise PermissionError(
            f"tenant violation: record belongs to '{record_tenant}', "
            f"current tenant is '{get_current_tenant()}'"
        )


def with_tenant(tenant: str):
    """Context manager for setting/restoring tenant in non-async blocks."""
    from contextlib import contextmanager
    @contextmanager
    def _ctx():
        token = _current_tenant.set(tenant)
        try:
            yield
        finally:
            _current_tenant.reset(token)
    return _ctx()
