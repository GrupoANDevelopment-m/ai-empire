"""
HITL approval HTTP API.

Mount this on the LangGraph orchestrator alongside /chat.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .hitl import HITLStore

router = APIRouter(prefix="/approvals", tags=["approvals"])
_store: HITLStore | None = None


async def get_store() -> HITLStore:
    global _store
    if _store is None:
        _store = HITLStore()
        await _store.init()
    return _store


@router.get("/pending")
async def list_pending(tenant: str = "default"):
    store = await get_store()
    items = await store.list_pending(tenant)
    return {
        "count": len(items),
        "approvals": [
            {
                "id": r.id,
                "action": r.action,
                "target": r.target,
                "args": r.args,
                "created_at": r.created_at,
                "expires_at": r.expires_at,
                "actor": r.actor,
            }
            for r in items
        ],
    }


@router.post("/{approval_id}/approve")
async def approve(approval_id: str, body: dict | None = None):
    store = await get_store()
    decided_by = (body or {}).get("decided_by", "admin")
    try:
        req = await store.decide(approval_id, approved=True, decided_by=decided_by)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": req.id, "status": req.status.value, "decided_by": req.decided_by}


@router.post("/{approval_id}/reject")
async def reject(approval_id: str, body: dict | None = None):
    store = await get_store()
    decided_by = (body or {}).get("decided_by", "admin")
    reason = (body or {}).get("reason", "")
    try:
        req = await store.decide(approval_id, approved=False, decided_by=decided_by,
                                 result={"reason": reason})
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": req.id, "status": req.status.value, "reason": reason}
