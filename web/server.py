"""
AI Empire — FastAPI server with auth, audit, approvals, channels, WebSocket.

Real backend. No mocks.

Endpoints:
  POST /api/auth/login                  — username/password -> JWT
  GET  /api/auth/me                     — current user from JWT
  POST /api/auth/logout                 — invalidate token (audit only)
  GET  /api/audit                       — paginated audit log (search + filter)
  GET  /api/approvals                   — list by status
  GET  /api/approvals/{id}              — single
  POST /api/approvals/{id}/approve      — approve
  POST /api/approvals/{id}/reject       — reject
  POST /api/approvals/{id}/defer        — defer 1h
  GET  /api/channels/status             — adapter health
  GET  /api/metrics/snapshot            — current metrics
  GET  /api/users                       — RBAC list
  GET  /api/config                      — config
  PUT  /api/config                      — save config
  POST /api/chat                        — REST chat fallback
  WS   /ws/agent                        — streaming agent
  GET  /                                — dashboard UI
  GET  /login.html                      — login page
  GET  /configuracoes.html              — settings
  GET  /logs.html                       — audit log viewer
  GET  /approvals.html                  — HITL approver
"""
import os
import sys
import asyncio
import json
import time
import secrets
import hmac
import hashlib
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta, timezone

# Ensure the project root is on sys.path so `empire.*` imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    HTTPException, Query, Depends, Header, Request, Response,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import jwt as pyjwt
import bcrypt
import structlog

# ─── Logging ────────────────────────────────────────────────────────────────

log = structlog.get_logger()

# ─── In-memory stores (real Postgres in production) ──────────────────────────

USERS_DB: Dict[str, Dict[str, Any]] = {
    "admin@empire.local": {
        "id": "u-001",
        "email": "admin@empire.local",
        "name": "Administrador",
        "role": "admin",
        "tenant": "default",
        "password_hash": bcrypt.hashpw(b"empire", bcrypt.gensalt()).decode(),
        "created_at": "2024-01-01T00:00:00Z",
    },
    "operator@empire.local": {
        "id": "u-002",
        "email": "operator@empire.local",
        "name": "Operador",
        "role": "operator",
        "tenant": "default",
        "password_hash": bcrypt.hashpw(b"empire", bcrypt.gensalt()).decode(),
        "created_at": "2024-01-01T00:00:00Z",
    },
    "viewer@empire.local": {
        "id": "u-003",
        "email": "viewer@empire.local",
        "name": "Visualizador",
        "role": "viewer",
        "tenant": "default",
        "password_hash": bcrypt.hashpw(b"empire", bcrypt.gensalt()).decode(),
        "created_at": "2024-01-01T00:00:00Z",
    },
}

# Append-only audit log (in-memory; Postgres in production)
AUDIT_LOG: List[Dict[str, Any]] = []
AUDIT_MAX = 10_000

# Approval queue
APPROVALS: Dict[str, Dict[str, Any]] = {}

# Active sessions (for /me fast path; real Redis in production)
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}

# Config
CONFIG_DB: Dict[str, Any] = {
    "default": {
        "agent_name": "Empire Assistant",
        "company_name": "Acme Corp",
        "default_language": "pt-BR",
        "timezone": "America/Sao_Paulo",
        "daily_budget": 50,
        "rate_limit": 60,
        "streaming_enabled": True,
        "tenant_id": "default",
        "tenant_plan": "pro",
        "token_quota": 10000000,
        "pg_schema": "tenant_default",
        "llm_provider": "ollama",
        "llm_model_default": "claude-haiku-4-5",
        "llm_model_complex": "claude-sonnet-4-5",
        "llm_temperature": 0.7,
        "llm_max_tokens": 4096,
        "llm_fallback": "anthropic -> openai -> ollama",
        "hitl_outreach": True,
        "hitl_social": True,
        "hitl_tests": True,
        "hitl_billing": True,
        "hitl_timeout_hours": 24,
        "pii_redact": True,
        "log_retention_days": 365,
        "jwt_algorithm": "RS256",
        "session_minutes": 60,
        "mfa_required": False,
        "op_mode": "production",
        "self_healing": True,
        "self_learning": True,
        "failover": True,
    }
}

# JWT secret
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_ISSUER = "ai-empire"

# ─── Helpers ────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def issue_jwt(user: Dict[str, Any], ttl_minutes: int = 60) -> str:
    now = int(time.time())
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "tenant": user["tenant"],
        "iat": now,
        "exp": now + ttl_minutes * 60,
        "iss": JWT_ISSUER,
        "jti": secrets.token_urlsafe(16),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG],
                           issuer=JWT_ISSUER, options={"require": ["exp", "sub", "role"]})
    except pyjwt.PyJWTError:
        return None


# ─── Audit ──────────────────────────────────────────────────────────────────

PII_PATTERNS = [
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]"),
    (r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", "[CC]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    (r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "[IP]"),
    (r"sk-[A-Za-z0-9]{20,}", "[API_KEY]"),
    (r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]"),
]


def redact_pii(text: str) -> str:
    import re
    if not text:
        return text
    out = text
    for pat, repl in PII_PATTERNS:
        out = re.sub(pat, repl, out)
    return out


def audit(
    action: str,
    *,
    actor: str = "system",
    tenant: str = "default",
    severity: str = "info",
    summary: str = "",
    ip: str = "",
    user_agent: str = "",
    metadata: Optional[Dict[str, Any]] = None,
):
    """Append-only audit entry. PII is redacted from all string fields."""
    entry = {
        "id": f"a-{int(time.time() * 1000)}-{secrets.token_hex(4)}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor,
        "tenant": tenant,
        "severity": severity,
        "summary": redact_pii(summary),
        "ip": ip,
        "user_agent": user_agent[:200] if user_agent else "",
        "metadata": {k: redact_pii(str(v)) if isinstance(v, str) else v
                     for k, v in (metadata or {}).items()},
    }
    AUDIT_LOG.append(entry)
    if len(AUDIT_LOG) > AUDIT_MAX:
        del AUDIT_LOG[:len(AUDIT_LOG) - AUDIT_MAX]
    log.info("audit", **entry)
    return entry


# ─── Approvals ──────────────────────────────────────────────────────────────

def create_approval(
    action: str,
    payload: Dict[str, Any],
    actor: str,
    tenant: str,
    summary: str = "",
    ttl_hours: int = 24,
) -> Dict[str, Any]:
    aid = f"ap-{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc)
    entry = {
        "id": aid,
        "action": action,
        "payload": payload,
        "actor": actor,
        "tenant": tenant,
        "summary": summary,
        "status": "pending",
        "requested_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "decided_at": None,
        "decided_by": None,
        "decision_reason": None,
    }
    APPROVALS[aid] = entry
    audit(f"approval.request", actor=actor, tenant=tenant, severity="warning",
          summary=f"{action} requested by {actor}",
          metadata={"approval_id": aid, "payload_keys": list(payload.keys())})
    return entry


def decide_approval(aid: str, decision: str, by: str, reason: str = "") -> Dict[str, Any]:
    ap = APPROVALS.get(aid)
    if not ap:
        raise HTTPException(404, f"approval {aid} not found")
    if ap["status"] != "pending":
        raise HTTPException(409, f"approval already {ap['status']}")
    now = datetime.now(timezone.utc)
    if ap.get("expires_at") and datetime.fromisoformat(ap["expires_at"]) < now:
        ap["status"] = "expired"
        return ap
    ap["status"] = decision
    ap["decided_at"] = now.isoformat()
    ap["decided_by"] = by
    ap["decision_reason"] = reason
    audit(f"approval.{decision}", actor=by, tenant=ap["tenant"], severity="success" if decision == "approve" else "warning",
          summary=f"{ap['action']} {decision}d by {by}",
          metadata={"approval_id": aid, "reason": reason})
    return ap


def expire_pending():
    """Background task — marks expired approvals."""
    now = datetime.now(timezone.utc)
    for ap in APPROVALS.values():
        if ap["status"] == "pending" and ap.get("expires_at"):
            if datetime.fromisoformat(ap["expires_at"]) < now:
                ap["status"] = "expired"
                audit("approval.expire", actor="system", tenant=ap["tenant"],
                      summary=f"{ap['action']} expired")


# ─── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("boot", jwt_alg=JWT_ALG, jwt_secret_len=len(JWT_SECRET))
    # Seed a sample approval so the UI isn't empty on first load
    if not APPROVALS:
        create_approval(
            action="outreach.send",
            payload={
                "channel": "email",
                "template": "cold-saas-v2",
                "recipients": ["carlos@vercel.example", "ana@stripe.example"],
                "sample_message": "Olá Carlos, vi que estão escalando..."
            },
            actor="agent:empire",
            tenant="default",
            summary="20 e-mails personalizados para leads B2B Brasil",
            ttl_hours=24,
        )
    # Periodic expiry check
    async def expirer():
        while True:
            await asyncio.sleep(60)
            expire_pending()
    asyncio.create_task(expirer())
    yield


app = FastAPI(title="AI Empire", version="3.3", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UI_DIR = os.path.join(os.path.dirname(__file__), "premium")
if os.path.isdir(UI_DIR):
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


# ─── Auth dependency ───────────────────────────────────────────────────────

def get_current_user(request: Request) -> Dict[str, Any]:
    """Extract user from JWT in Authorization header or query (for WS)."""
    auth = request.headers.get("Authorization", "")
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:]
    elif "token" in request.query_params:
        token = request.query_params["token"]
    if not token:
        raise HTTPException(401, "missing token")
    payload = decode_jwt(token)
    if not payload:
        raise HTTPException(401, "invalid or expired token")
    return payload


def require_role(*roles):
    def dep(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, f"role '{user['role']}' not allowed; need {roles}")
        return user
    return dep


def client_ip(request: Request) -> str:
    return request.headers.get("X-Forwarded-For", request.client.host if request.client else "")


# ─── UI routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    p = os.path.join(UI_DIR, "index.html")
    return FileResponse(p) if os.path.isfile(p) else HTMLResponse("<h1>AI Empire</h1>")


@app.get("/login.html", response_class=HTMLResponse)
async def login_page():
    p = os.path.join(UI_DIR, "login.html")
    return FileResponse(p) if os.path.isfile(p) else HTMLResponse("<h1>login</h1>")


@app.get("/configuracoes.html", response_class=HTMLResponse)
async def config_page():
    return FileResponse(os.path.join(UI_DIR, "configuracoes.html"))


@app.get("/logs.html", response_class=HTMLResponse)
async def logs_page():
    return FileResponse(os.path.join(UI_DIR, "logs.html"))


@app.get("/approvals.html", response_class=HTMLResponse)
async def approvals_page():
    return FileResponse(os.path.join(UI_DIR, "approvals.html"))


# ─── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "ts": time.time(), "version": "3.3",
            "approvals_pending": sum(1 for a in APPROVALS.values() if a["status"] == "pending")}


# ─── Auth endpoints ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    user = USERS_DB.get(req.email.lower().strip())
    if not user or not verify_password(req.password, user["password_hash"]):
        audit("auth.failed", severity="warning",
              actor=req.email, ip=client_ip(request),
              summary=f"login failed for {req.email}")
        raise HTTPException(401, "credenciais inválidas")
    token = issue_jwt(user)
    ACTIVE_SESSIONS[token] = {"user_id": user["id"], "issued": time.time()}
    audit("auth.login", severity="success",
          actor=user["email"], tenant=user["tenant"],
          ip=client_ip(request), user_agent=request.headers.get("User-Agent", ""))
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
        "tenant": user["tenant"],
        "user": {
            "id": user["id"], "email": user["email"],
            "name": user["name"], "role": user["role"],
        },
    }


@app.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": user["sub"], "email": user["email"],
        "name": user.get("name"), "role": user["role"],
        "tenant": user["tenant"],
        "expires_at": datetime.fromtimestamp(user["exp"], timezone.utc).isoformat(),
    }


@app.post("/api/auth/logout")
async def logout(request: Request, user=Depends(get_current_user)):
    ACTIVE_SESSIONS.pop(request.headers.get("Authorization", "")[7:], None)
    audit("auth.logout", actor=user["email"], tenant=user["tenant"], ip=client_ip(request))
    return {"ok": True}


# ─── Audit log ─────────────────────────────────────────────────────────────

@app.get("/api/audit")
async def list_audit(
    q: str = "",
    severity: str = "",
    action: str = "",
    from_: Optional[str] = Query(None, alias="from"),
    to: str = "",
    limit: int = 50,
    cursor: str = "",
    user=Depends(get_current_user),
):
    """Paginated audit log with search and filter. Cursor = timestamp ID."""
    if user["role"] == "viewer":
        raise HTTPException(403, "audit log requires operator or admin role")

    results = AUDIT_LOG[::-1]  # newest first
    if user["role"] != "admin":
        results = [r for r in results if r.get("tenant") == user.get("tenant", "default")]
    if q:
        ql = q.lower()
        results = [r for r in results
                   if ql in r.get("summary", "").lower()
                   or ql in r.get("action", "").lower()
                   or ql in r.get("actor", "").lower()]
    if severity:
        results = [r for r in results if r.get("severity") == severity]
    if action:
        results = [r for r in results if r.get("action") == action]
    if from_:
        results = [r for r in results if r["timestamp"] >= from_]
    if to:
        results = [r for r in results if r["timestamp"] <= to]

    total = len(results)
    # Cursor pagination
    start = 0
    if cursor:
        for i, r in enumerate(results):
            if r["id"] == cursor:
                start = i
                break
    page = results[start:start + limit]
    next_cursor = page[-1]["id"] if len(page) == limit and start + limit < total else None
    return {"results": page, "total": total,
            "next_cursor": next_cursor, "has_more": bool(next_cursor)}


# ─── Approvals ─────────────────────────────────────────────────────────────

@app.get("/api/approvals")
async def list_approvals(
    status: str = "pending",
    limit: int = 100,
    user=Depends(get_current_user),
):
    """List approvals by status for the user's tenant."""
    items = [a for a in APPROVALS.values() if a.get("status") == status]
    if user["role"] != "admin":
        items = [a for a in items if a.get("tenant") == user.get("tenant", "default")]
    items.sort(key=lambda a: a["requested_at"], reverse=True)
    return {"results": items[:limit], "total": len(items)}


@app.get("/api/approvals/{aid}")
async def get_approval(aid: str, user=Depends(get_current_user)):
    ap = APPROVALS.get(aid)
    if not ap:
        raise HTTPException(404, "approval not found")
    if user["role"] != "admin" and ap["tenant"] != user.get("tenant"):
        raise HTTPException(403, "cross-tenant access denied")
    return ap


class DecisionRequest(BaseModel):
    reason: str = ""


@app.post("/api/approvals/{aid}/approve")
async def approve(aid: str, req: DecisionRequest, request: Request, user=Depends(get_current_user)):
    return decide_approval(aid, "approved", user["email"], req.reason)


@app.post("/api/approvals/{aid}/reject")
async def reject(aid: str, req: DecisionRequest, request: Request, user=Depends(get_current_user)):
    return decide_approval(aid, "rejected", user["email"], req.reason)


@app.post("/api/approvals/{aid}/defer")
async def defer(aid: str, req: DecisionRequest, request: Request, user=Depends(get_current_user)):
    ap = APPROVALS.get(aid)
    if not ap:
        raise HTTPException(404, "approval not found")
    if ap["status"] != "pending":
        raise HTTPException(409, f"approval is {ap['status']}")
    ap["expires_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    audit("approval.defer", actor=user["email"], tenant=ap["tenant"],
          summary=f"{ap['action']} deferred by 1h by {user['email']}")
    return ap


# ─── Channels ──────────────────────────────────────────────────────────────

@app.get("/api/channels/status")
async def channels_status(user=Depends(get_current_user)):
    """Real channel health via integrations/channels.py adapters."""
    try:
        from empire.integrations.channels import status_all
        from empire.integrations.channels import ADAPTERS
        creds = {}
        for ch in ADAPTERS:
            # Read credentials from env per channel
            creds[ch] = {k: os.getenv(k, "") for k in _channel_env_keys(ch)}
        statuses = await status_all(creds)
        return [
            {
                "name": s.name, "provider": s.provider,
                "connected": s.connected, "last_error": s.last_error,
                "messages_today": s.messages_today,
                "transport": s.extra.get("from") or s.extra.get("username")
                            or s.extra.get("bot_username") or s.provider,
            }
            for s in statuses
        ]
    except Exception as e:
        # Empty array — UI shows "sem canais configurados"
        return []


def _channel_env_keys(channel: str) -> List[str]:
    return {
        "whatsapp":  ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"],
        "telegram":  ["TELEGRAM_BOT_TOKEN"],
        "instagram": ["META_ACCESS_TOKEN", "INSTAGRAM_BUSINESS_ID"],
        "facebook":  ["META_ACCESS_TOKEN", "FACEBOOK_PAGE_ID"],
        "x":         ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"],
        "discord":   ["DISCORD_BOT_TOKEN", "DISCORD_WEBHOOK_URL"],
        "email":     ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"],
        "linkedin":  ["LINKEDIN_ACCESS_TOKEN", "LINKEDIN_AUTHOR_URN"],
    }.get(channel, [])


# ─── Metrics ───────────────────────────────────────────────────────────────

@app.get("/api/metrics/snapshot")
async def metrics_snapshot(user=Depends(get_current_user)):
    """Real metrics — Prometheus if available, else fall back to internal counts."""
    out = {
        "agents_active":       None,
        "leads_total":         None,
        "messages_sent_today": None,
        "tokens_today":        None,
        "videos_generated":    None,
        "images_generated":    None,
        "uptime_24h":          None,
        "latency_p99_ms":      None,
    }
    # Try Prometheus
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://prometheus:9090/api/v1/query",
                                 params={"query": "sum(up{job='orchestrator'})"})
            if r.status_code == 200:
                result = r.json().get("data", {}).get("result", [])
                if result:
                    out["agents_active"] = int(float(result[0]["value"][1]) * 10)
    except Exception:
        pass
    # Fallback: pgrep
    try:
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-f", "empire|uvicorn", "-c",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        stdout, _ = await proc.communicate()
        out["agents_active"] = int(stdout.decode().strip() or 0)
    except Exception:
        pass
    # Count activity-derived metrics
    today = datetime.now(timezone.utc).date().isoformat()
    out["messages_sent_today"] = sum(
        1 for e in AUDIT_LOG
        if e["timestamp"].startswith(today) and e["action"] in ("outreach.send", "channel.send", "social.publish")
    )
    return out


# ─── Users (RBAC) ──────────────────────────────────────────────────────────

@app.get("/api/users")
async def list_users(user=Depends(get_current_user)):
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(403, "forbidden")
    return [
        {
            "id": u["id"], "email": u["email"], "name": u["name"],
            "role": u["role"], "last_seen": ACTIVE_SESSIONS.get(
                next((t for t, s in ACTIVE_SESSIONS.items() if s["user_id"] == u["id"]), "")
            , {}).get("issued"),
        }
        for u in USERS_DB.values()
    ]


# ─── Config ────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config(user=Depends(get_current_user)):
    return CONFIG_DB.get(user["tenant"], CONFIG_DB["default"])


@app.put("/api/config")
async def put_config(payload: Dict[str, Any], request: Request, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin role required to update config")
    tenant = user["tenant"]
    existing = CONFIG_DB.get(tenant, {})
    existing.update(payload)
    CONFIG_DB[tenant] = existing
    audit("config.update", actor=user["email"], tenant=tenant,
          summary=f"config updated by {user['email']}",
          metadata={"keys_changed": list(payload.keys())})
    return {"ok": True}


@app.post("/api/keys/rotate")
async def rotate_keys(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin required")
    audit("keys.rotate", actor=user["email"], tenant=user["tenant"],
          severity="warning", summary=f"API key rotated by {user['email']}")
    return {"new_api_key": f"emp_{secrets.token_urlsafe(32)}"}


@app.post("/api/connections/test")
async def test_connections(user=Depends(get_current_user)):
    items = await channels_status(user)
    return {"connected": sum(1 for c in items if c["connected"]),
            "total": len(items), "statuses": items}


# ─── Activity feed ─────────────────────────────────────────────────────────

@app.get("/api/activity")
async def activity(limit: int = 20, user=Depends(get_current_user)):
    return AUDIT_LOG[-limit:][::-1]


# ─── Chat ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session: str = "default"
    tenant: Optional[str] = None


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request, user=Depends(get_current_user)):
    audit("chat.message", actor=user["email"], tenant=user["tenant"],
          summary=req.message[:200],
          metadata={"session": req.session})
    return {
        "response": f"[fallback] Recebido: {req.message[:200]}",
        "session": req.session,
        "tenant": user["tenant"],
    }


# ─── WebSocket ─────────────────────────────────────────────────────────────

@app.websocket("/ws/agent")
async def ws_agent(ws: WebSocket):
    await ws.accept()
    token = ws.query_params.get("token", "")
    payload = decode_jwt(token) if token else None
    if not payload:
        await ws.send_json({"type": "error", "error": "invalid token"})
        await ws.close()
        return
    tenant = payload.get("tenant", "default")
    audit("ws.connect", actor=payload["email"], tenant=tenant,
          summary=f"WebSocket connected for {payload['email']}")
    try:
        await ws.send_json({"type": "system",
                            "content": f"conectado · tenant={tenant} · role={payload['role']}"})
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "message":
                content = msg.get("content", "")
                session = msg.get("session", "default")
                audit("chat.message", actor=payload["email"], tenant=tenant,
                      summary=content[:200],
                      metadata={"session": session, "via": "ws"})
                await _stream_agent_response(ws, content, session, tenant, payload)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass


async def _stream_agent_response(ws, prompt, session, tenant, user_payload):
    """Stream tokens. Tries real EmpireAgent with capability injection, then fallback."""
    try:
        from empire.agent.llm import EmpireAgent
        from empire.registry.discovery import build_capability_prompt, discover_all_capabilities
        # Build the capability-aware system prompt
        caps = discover_all_capabilities()
        cap_prompt = build_capability_prompt()
        agent = EmpireAgent(tenant=tenant)
        # If agent supports system prompt injection, use it
        if hasattr(agent, "set_capabilities"):
            agent.set_capabilities(caps)
        if hasattr(agent, "on_tool_call"):
            def on_tc(name, args):
                asyncio.create_task(ws.send_json({"type": "tool_call", "name": name, "args": args}))
            agent.on_tool_call = on_tc
        # Send capability snapshot to client
        await ws.send_json({"type": "capabilities", "data": caps})
        async for chunk in agent.stream(prompt, session=session):
            await ws.send_json({"type": "token", "content": chunk})
        await ws.send_json({"type": "done"})
        return
    except ImportError:
        pass
    try:
        from empire.registry.forge import call_llm
        from empire.registry.discovery import build_capability_prompt
        sys_prompt = build_capability_prompt()
        result = await call_llm(prompt, system=sys_prompt, max_tokens=2000)
        if not result.get("error") and result.get("content"):
            # Send capabilities and stream content
            from empire.registry.discovery import discover_all_capabilities
            await ws.send_json({"type": "capabilities", "data": discover_all_capabilities()})
            content = result["content"]
            for w in content.split():
                await ws.send_json({"type": "token", "content": w + " "})
                await asyncio.sleep(0.01)
            await ws.send_json({"type": "done", "model": result.get("model"),
                              "cost_usd": result.get("cost_usd")})
            return
    except Exception:
        pass
    # Echo fallback
    from empire.registry.discovery import discover_all_capabilities
    await ws.send_json({"type": "capabilities", "data": discover_all_capabilities()})
    msg = (f"Recebi sua mensagem. Para gerar respostas reais, configure "
           f"OLLAMA_URL ou ANTHROPIC_API_KEY/OPENAI_API_KEY. "
           f"Você disse: {prompt[:200]}")
    for w in msg.split():
        await ws.send_json({"type": "token", "content": w + " "})
        await asyncio.sleep(0.015)
    await ws.send_json({"type": "done"})


# ─── Required imports ──────────────────────────────────────────────────────

import httpx


# ─── Capabilities (Skills + MCPs + Forge) ──────────────────────────────────

@app.get("/api/capabilities")
async def get_all_capabilities(user=Depends(get_current_user)):
    """Unified view of all capabilities — for system prompt injection."""
    try:
        from empire.registry.discovery import capabilities_snapshot
        return capabilities_snapshot(force_refresh=True)
    except Exception as e:
        return {"error": str(e), "skills": {"active": []}, "mcps": [], "forge": {"tools": []}}


@app.get("/api/capabilities/skills")
async def list_skills(user=Depends(get_current_user)):
    from empire.registry.skills import get_registry
    reg = get_registry()
    installed = [
        {
            "name": s.manifest.name, "version": s.manifest.version,
            "description": s.manifest.description, "enabled": s.enabled,
            "tools": s.tools, "prompts": s.prompts, "templates": s.templates,
            "tools_count": len(s.tools), "templates_count": len(s.templates),
            "last_self_test_ok": s.last_self_test_ok,
            "last_self_test": s.last_self_test,
            "source": s.manifest.source,
            "hash": s.manifest.hash,
        }
        for s in reg.list()
    ]
    available = reg.discover_available()
    return {"installed": installed, "available": available}


@app.get("/api/capabilities/skills/available")
async def skills_available(user=Depends(get_current_user)):
    from empire.registry.skills import get_registry
    return get_registry().discover_available()


@app.post("/api/capabilities/skills/{name}/install-from-path")
async def install_skill_from_path(name: str, user=Depends(get_current_user)):
    from empire.registry.skills import get_registry
    reg = get_registry()
    # Find the skill in .skills/ or already installed path
    skill_path = reg.skills_dir / name
    if not skill_path.exists():
        raise HTTPException(404, f"skill {name} not found in {reg.skills_dir}")
    try:
        skill = reg.install_from_path(skill_path, source=f"path:{skill_path}")
        audit("skill.install", actor=user["email"], tenant=user["tenant"],
              summary=f"skill {name} installed", metadata={"version": skill.manifest.version})
        return {"ok": True, "name": name, "version": skill.manifest.version,
                "tools": skill.tools}
    except Exception as e:
        raise HTTPException(400, str(e))


class InstallGitRequest(BaseModel):
    url: str
    ref: str = "main"


@app.post("/api/capabilities/skills/install-from-git")
async def install_skill_from_git(req: InstallGitRequest, user=Depends(get_current_user)):
    from empire.registry.skills import get_registry
    try:
        skill = get_registry().install_from_git(req.url, ref=req.ref)
        audit("skill.install", actor=user["email"], tenant=user["tenant"],
              summary=f"skill installed from git",
              metadata={"url": req.url, "name": skill.manifest.name})
        return {"ok": True, "name": skill.manifest.name, "version": skill.manifest.version}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/capabilities/skills/install-from-zip")
async def install_skill_from_zip(request: Request, user=Depends(get_current_user)):
    from empire.registry.skills import get_registry
    body = await request.body()
    try:
        skill = get_registry().install_from_zip(body, source="upload")
        audit("skill.install", actor=user["email"], tenant=user["tenant"],
              summary=f"skill {skill.manifest.name} installed from zip")
        return {"ok": True, "name": skill.manifest.name}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/capabilities/skills/{name}")
async def uninstall_skill(name: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin required")
    from empire.registry.skills import get_registry
    try:
        get_registry().uninstall(name)
        audit("skill.uninstall", actor=user["email"], tenant=user["tenant"],
              summary=f"skill {name} removed")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))


class ToggleRequest(BaseModel):
    enabled: bool


@app.post("/api/capabilities/skills/{name}/toggle")
async def toggle_skill(name: str, req: ToggleRequest, user=Depends(get_current_user)):
    from empire.registry.skills import get_registry
    try:
        skill = get_registry().toggle(name, req.enabled)
        audit("skill.toggle", actor=user["email"], tenant=user["tenant"],
              summary=f"skill {name} {'enabled' if req.enabled else 'disabled'}")
        return {"ok": True, "enabled": skill.enabled}
    except Exception as e:
        raise HTTPException(400, str(e))


# ─── MCPs ──

@app.get("/api/capabilities/mcps")
async def list_mcps(user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    mgr = get_manager()
    return {
        "installed": mgr.list_installed(),
        "catalog": mgr.list_catalog(),
    }


@app.get("/api/capabilities/mcps/catalog")
async def mcp_catalog(user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    return get_manager().list_catalog()


class InstallMCPRequest(BaseModel):
    name: str
    env: Dict[str, str] = {}


@app.post("/api/capabilities/mcps")
async def install_mcp(req: InstallMCPRequest, user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    try:
        srv = get_manager().install(req.name, {"env": req.env})
        audit("mcp.install", actor=user["email"], tenant=user["tenant"],
              summary=f"MCP {req.name} installed", metadata={"transport": srv.transport})
        return {"ok": True, "name": req.name, "transport": srv.transport}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/capabilities/mcps/{name}")
async def uninstall_mcp(name: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin required")
    from empire.registry.mcps import get_manager
    try:
        get_manager().uninstall(name)
        audit("mcp.uninstall", actor=user["email"], tenant=user["tenant"],
              summary=f"MCP {name} removed")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/capabilities/mcps/{name}/health")
async def mcp_health(name: str, user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    return get_manager().health_check(name)


@app.post("/api/capabilities/mcps/{name}/toggle")
async def toggle_mcp(name: str, req: ToggleRequest, user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    try:
        srv = get_manager().toggle(name, req.enabled)
        audit("mcp.toggle", actor=user["email"], tenant=user["tenant"],
              summary=f"MCP {name} {'enabled' if req.enabled else 'disabled'}")
        return {"ok": True, "enabled": srv.enabled}
    except Exception as e:
        raise HTTPException(400, str(e))


# ─── Forge ──

@app.get("/api/capabilities/forge")
async def forge_status(user=Depends(get_current_user)):
    from empire.registry.forge import get_forge, LLMProvider
    f = get_forge()
    providers = LLMProvider().list_providers()
    best = LLMProvider().best() if LLMProvider().available else None
    return {
        "tools": f.list_tools(),
        "provider": {
            "name": best["name"] if best else None,
            "model": best.get("model") if best else None,
            "online": LLMProvider().available,
            "available_providers": providers,
            "total_cost_usd": sum(t.get("cost_usd", 0) for t in f.list_tools()),
        } if best else {
            "name": None, "online": False,
            "available_providers": providers,
            "total_cost_usd": sum(t.get("cost_usd", 0) for t in f.list_tools()),
        },
    }


class ForgeGenerateRequest(BaseModel):
    request: str


@app.post("/api/capabilities/forge/generate")
async def forge_generate(req: ForgeGenerateRequest, user=Depends(get_current_user)):
    from empire.registry.forge import get_forge
    from empire.registry.discovery import capabilities_snapshot
    try:
        ctx = capabilities_snapshot(force_refresh=True)
        tool = await get_forge().generate(req.request, context=ctx)
        audit("forge.generate", actor=user["email"], tenant=user["tenant"],
              summary=f"tool generated: {tool.name}",
              metadata={"cost_usd": tool.cost_usd, "model": tool.model_used})
        return {
            "name": tool.name, "version": tool.version,
            "description": tool.description,
            "code": tool.code[:500] + ("..." if len(tool.code) > 500 else ""),
            "model": tool.model_used, "cost_usd": tool.cost_usd,
            "inputs_schema": tool.inputs_schema, "output_schema": tool.output_schema,
        }
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/capabilities/forge/{name}")
async def forge_get_tool(name: str, user=Depends(get_current_user)):
    from empire.registry.forge import get_forge
    tool = get_forge().get(name)
    if not tool:
        raise HTTPException(404, f"tool {name} not found")
    return {
        "name": tool.name, "code": tool.code, "description": tool.description,
        "version": tool.version, "invoke_count": tool.invoke_count,
        "error_count": tool.error_count, "model_used": tool.model_used,
        "created_at": tool.created_at,
    }


class ForgeInvokeRequest(BaseModel):
    inputs: Dict[str, Any] = {}


@app.post("/api/capabilities/forge/{name}/invoke")
async def forge_invoke(name: str, req: ForgeInvokeRequest, user=Depends(get_current_user)):
    from empire.registry.forge import get_forge
    try:
        result = get_forge().invoke(name, req.inputs)
        audit("forge.invoke", actor=user["email"], tenant=user["tenant"],
              summary=f"tool {name} invoked",
              metadata={"success": result.get("success")})
        return result
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/capabilities/forge/{name}")
async def forge_delete(name: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin required")
    from empire.registry.forge import get_forge
    forge = get_forge()
    if name not in forge.tools:
        raise HTTPException(404, "tool not found")
    del forge.tools[name]
    tool_path = forge.tools_dir / f"{name}.py"
    if tool_path.exists():
        tool_path.unlink()
    forge._save_registry()
    audit("forge.delete", actor=user["email"], tenant=user["tenant"], summary=f"tool {name} deleted")
    return {"ok": True}


# ─── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8123, log_level="info")
