"""
Human-in-the-loop approval flow.

Wraps dangerous tool calls (send_outreach, publish_social, etc.) so that
they PAUSE before executing and wait for human approval. The human
responds via:
  POST /approvals/{approval_id}/approve   → tool runs
  POST /approvals/{approval_id}/reject    → tool cancelled
  GET  /approvals/pending                  → list pending approvals

Persistence: Postgres (approval_id, status, expires_at, args, result).
"""
import os
import uuid
import time
import json
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import asyncpg


class ApprovalStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED  = "expired"
    AUTO_APPROVED = "auto_approved"  # for trusted operators


@dataclass
class ApprovalRequest:
    id: str
    tenant: str
    actor: str
    action: str
    target: str
    args: dict
    created_at: float
    expires_at: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str = ""
    decided_at: float = 0.0
    result: Any = None


# Tools that ALWAYS need human approval, regardless of role
DEFAULT_REQUIRED_ACTIONS = {"send_outreach", "publish_social", "run_tests"}


class HITLStore:
    """Postgres-backed approval queue."""

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("DATABASE_URL",
                                   "postgresql://empire:empire@postgres:5432/ai_empire")
        self._pool: Optional[asyncpg.Pool] = None

    async def init(self):
        """Create schema if missing."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id           UUID PRIMARY KEY,
                    tenant       TEXT NOT NULL,
                    actor        TEXT NOT NULL,
                    action       TEXT NOT NULL,
                    target       TEXT,
                    args         JSONB NOT NULL,
                    created_at   DOUBLE PRECISION NOT NULL,
                    expires_at   DOUBLE PRECISION NOT NULL,
                    status       TEXT NOT NULL,
                    decided_by   TEXT,
                    decided_at   DOUBLE PRECISION,
                    result       JSONB
                );
                CREATE INDEX IF NOT EXISTS idx_approvals_tenant_status
                  ON approvals(tenant, status);
                CREATE INDEX IF NOT EXISTS idx_approvals_expires
                  ON approvals(expires_at) WHERE status = 'pending';
            """)

    async def create(self, tenant: str, actor: str, action: str,
                     args: dict, target: str = "",
                     ttl_seconds: int = 3600) -> ApprovalRequest:
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            tenant=tenant,
            actor=actor,
            action=action,
            target=target,
            args=args,
            created_at=time.time(),
            expires_at=time.time() + ttl_seconds,
        )
        await self.init()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO approvals (id, tenant, actor, action, target, args, created_at, expires_at, status) "
                "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)",
                req.id, req.tenant, req.actor, req.action, req.target,
                json.dumps(req.args), req.created_at, req.expires_at, req.status.value,
            )
        return req

    async def get(self, approval_id: str) -> Optional[ApprovalRequest]:
        await self.init()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM approvals WHERE id = $1", uuid.UUID(approval_id),
            )
            if not row:
                return None
            return self._from_row(row)

    async def list_pending(self, tenant: str = "default") -> list[ApprovalRequest]:
        await self.init()
        # Expire old ones on read
        now = time.time()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE approvals SET status='expired' WHERE status='pending' AND expires_at < $1",
                now,
            )
            rows = await conn.fetch(
                "SELECT * FROM approvals WHERE tenant = $1 AND status = 'pending' ORDER BY created_at DESC",
                tenant,
            )
            return [self._from_row(r) for r in rows]

    async def decide(self, approval_id: str, approved: bool,
                     decided_by: str = "admin", result: Any = None) -> ApprovalRequest:
        await self.init()
        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE approvals SET status=$1, decided_by=$2, decided_at=$3, result=$4::jsonb "
                "WHERE id=$5 AND status='pending' RETURNING *",
                new_status.value, decided_by, time.time(),
                json.dumps(result) if result is not None else None,
                uuid.UUID(approval_id),
            )
        if not row:
            raise LookupError(f"approval {approval_id} not pending")
        return self._from_row(row)

    def _from_row(self, row) -> ApprovalRequest:
        return ApprovalRequest(
            id=str(row["id"]),
            tenant=row["tenant"],
            actor=row["actor"],
            action=row["action"],
            target=row["target"] or "",
            args=row["args"] if isinstance(row["args"], dict) else json.loads(row["args"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            status=ApprovalStatus(row["status"]),
            decided_by=row["decided_by"] or "",
            decided_at=row["decided_at"] or 0.0,
            result=row["result"] if row["result"] is None or isinstance(row["result"], (dict, list)) else json.loads(row["result"]),
        )


# ── Tool integration ─────────────────────────────────────────────────────────

async def request_approval_or_run(store: HITLStore, action: str, args: dict,
                                  run_fn, *, tenant: str = "default",
                                  actor: str = "agent",
                                  required: bool = None) -> tuple[str, Any]:
    """
    If `action` requires HITL approval, create an approval request and
    return a message asking for human input. Otherwise, run immediately.

    Returns: (message, result). If awaiting approval, result is None.
    """
    # Read env var that overrides the default required list
    raw = os.getenv("FEATURE_HITL_REQUIRED", "")
    if raw:
        required = {a.strip() for a in raw.split(",") if a.strip()}
    else:
        required = DEFAULT_REQUIRED_ACTIONS

    if action not in required:
        # Auto-run
        result = await run_fn(**args) if asyncio.iscoroutinefunction(run_fn) else run_fn(**args)
        return ("auto-approved and executed", result)

    # Otherwise, create approval and ask user
    req = await store.create(tenant=tenant, actor=actor, action=action,
                             target=args.get("target", args.get("lead_index", "")),
                             args=args, ttl_seconds=3600)
    return (
        f"⏸ awaiting human approval — ID: {req.id}\n"
        f"   action: {action}\n"
        f"   target: {req.target}\n"
        f"   args: {args}\n"
        f"   POST /approvals/{req.id}/approve  → execute\n"
        f"   POST /approvals/{req.id}/reject   → cancel",
        None,
    )
