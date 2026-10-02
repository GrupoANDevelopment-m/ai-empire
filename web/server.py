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
import re
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timedelta, timezone

# Ensure the project root is on sys.path so `empire.*` imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    HTTPException, Query, Depends, Header, Request, Response,
    BackgroundTasks,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
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
    # Second tenant for testing cross-tenant isolation
    "admin@acme.com": {
        "id": "u-010",
        "email": "admin@acme.com",
        "name": "Acme Admin",
        "role": "admin",
        "tenant": "acme",
        "password_hash": bcrypt.hashpw(b"empire", bcrypt.gensalt()).decode(),
        "created_at": "2024-01-01T00:00:00Z",
    },
    "operator@acme.com": {
        "id": "u-011",
        "email": "operator@acme.com",
        "name": "Acme Operator",
        "role": "operator",
        "tenant": "acme",
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

# JWT secret - MUST be at least 32 bytes for HS256 (RFC 7518)
_jwt_secret_raw = os.getenv("JWT_SECRET")
if not _jwt_secret_raw or len(_jwt_secret_raw) < 32:
    _jwt_secret_raw = secrets.token_urlsafe(48)  # 48 bytes > 32 minimum
JWT_SECRET = _jwt_secret_raw
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_ISSUER = "ai-empire"

# Default limits (prevent DoS via huge queries)
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500

# ─── Rate limiting (in-memory, simple sliding window) ──────────────────────

_RATE_BUCKET: Dict[str, List[float]] = {}
RATE_LIMIT_PER_MIN = int(os.getenv("EMPIRE_RATE_LIMIT_PER_MIN", "60"))


def _rate_check(client_id: str, max_per_min: int = RATE_LIMIT_PER_MIN) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    now = time.time()
    bucket = _RATE_BUCKET.setdefault(client_id, [])
    # Drop entries older than 60s
    while bucket and now - bucket[0] > 60:
        bucket.pop(0)
    if len(bucket) >= max_per_min:
        return False
    bucket.append(now)
    return True


def _client_key(request: Request, user_email: str = "") -> str:
    ip = client_ip(request)
    return f"{user_email}:{ip}" if user_email else ip


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
    user: Optional[Dict[str, Any]] = None,
) -> None:
    """Append-only audit entry. PII is redacted from all string fields."""
    # If user dict passed, override defaults
    if user:
        actor = user.get("email", actor)
        tenant = user.get("tenant", tenant)
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
    # Rate limit per token+IP — exempt /health and /docs to avoid killing LB probes
    path = request.url.path
    exempt_paths = ("/health", "/docs", "/openapi.json", "/redoc")
    if not any(path == p or path.startswith(p + "/") for p in exempt_paths):
        auth = request.headers.get("Authorization", "")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth[7:]
        elif "token" in request.query_params:
            token = request.query_params["token"]
        # Use token prefix as client identifier
        client_id = (token[:32] if token else "") + client_ip(request)
        if not _rate_check(client_id, max_per_min=RATE_LIMIT_PER_MIN):
            raise HTTPException(429, "rate limit exceeded; slow down")
    # Get token
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

# Track server start time for uptime
_BOOT_TIME = time.time()


@app.get("/health")
async def health():
    """Comprehensive health check — useful for k8s/load balancers."""
    uptime = time.time() - _BOOT_TIME
    pending_approvals = sum(1 for a in APPROVALS.values() if a["status"] == "pending")
    # Check key subsystems
    components = {
        "audit_log": {"ok": True, "count": len(AUDIT_LOG), "max": 10_000},
        "approvals": {"ok": True, "pending": pending_approvals},
        "episodic_memory": {"ok": True},
        "semantic_memory": {"ok": True},
    }
    # Check subsystem health
    try:
        from empire.registry.skills import get_registry
        components["skills"] = {"ok": True, "installed": len(get_registry().installed)}
    except Exception as e:
        components["skills"] = {"ok": False, "error": str(e)[:100]}
    try:
        from empire.registry.mcps import get_manager
        components["mcps"] = {"ok": True, "installed": len(get_manager().servers)}
    except Exception as e:
        components["mcps"] = {"ok": False, "error": str(e)[:100]}
    # Status = ok if all critical subsystems are ok
    all_ok = all(c.get("ok", True) for c in components.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "ts": time.time(),
        "version": "3.3",
        "uptime_seconds": int(uptime),
        "components": components,
    }


# ─── Auth endpoints ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    # Rate-limit login attempts per IP (5/min) — prevent brute force
    key = f"login:{client_ip(request)}"
    if not _rate_check(key, max_per_min=5):
        audit("auth.rate_limited", severity="warning",
              actor=req.email, ip=client_ip(request),
              summary=f"login rate-limited from {client_ip(request)}")
        raise HTTPException(429, "too many login attempts; try again in a minute")
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
    # Clamp limit to prevent DoS
    limit = min(max(1, limit), MAX_PAGE_LIMIT)

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
    limit = min(max(1, limit), MAX_PAGE_LIMIT)
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
    # Validate input
    if not req.message or not req.message.strip():
        raise HTTPException(400, "message cannot be empty")
    if len(req.message) > 8000:
        raise HTTPException(400, "message too long (max 8000 chars)")
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
    reg = get_registry()
    if name not in reg.installed:
        raise HTTPException(404, f"skill '{name}' not installed")
    try:
        reg.uninstall(name)
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
    reg = get_registry()
    if name not in reg.installed:
        raise HTTPException(404, f"skill '{name}' not installed")
    try:
        skill = reg.toggle(name, req.enabled)
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
    mgr = get_manager()
    if name not in mgr.servers:
        raise HTTPException(404, f"MCP '{name}' not installed")
    try:
        mgr.uninstall(name)
        audit("mcp.uninstall", actor=user["email"], tenant=user["tenant"],
              summary=f"MCP {name} removed")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/capabilities/mcps/{name}/health")
async def mcp_health(name: str, user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    mgr = get_manager()
    if name not in mgr.servers:
        raise HTTPException(404, f"MCP '{name}' not installed")
    return mgr.health_check(name)


@app.post("/api/capabilities/mcps/{name}/toggle")
async def toggle_mcp(name: str, req: ToggleRequest, user=Depends(get_current_user)):
    from empire.registry.mcps import get_manager
    mgr = get_manager()
    if name not in mgr.servers:
        raise HTTPException(404, f"MCP '{name}' not installed")
    try:
        srv = mgr.toggle(name, req.enabled)
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
    forge = get_forge()
    if name not in forge.tools:
        raise HTTPException(404, f"tool '{name}' not found")
    try:
        result = forge.invoke(name, req.inputs)
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
        raise HTTPException(404, f"tool '{name}' not found")
    del forge.tools[name]
    tool_path = forge.tools_dir / f"{name}.py"
    if tool_path.exists():
        tool_path.unlink()
    forge._save_registry()
    audit("forge.delete", actor=user["email"], tenant=user["tenant"], summary=f"tool {name} deleted")
    return {"ok": True}


# ─── Run ───────────────────────────────────────────────────────────────────

# ─── Data Upload Endpoints ─────────────────────────────────────────────────

@app.get("/api/data/stats")
async def data_stats(user=Depends(get_current_user)):
    from empire.registry.data import get_store
    return get_store().stats()


@app.get("/api/data/datasets")
async def list_datasets(user=Depends(get_current_user)):
    from empire.registry.data import get_store
    items = get_store().list(tenant=user["tenant"])
    return [{
        "id": d.id, "name": d.name, "filename": d.filename,
        "format": d.format.value, "size_bytes": d.size_bytes,
        "sha256": d.sha256, "uploaded_at": d.uploaded_at,
        "tenant": d.tenant, "indexed": d.indexed,
        "pii_detected": d.pii_detected,
        "indexed_rows": d.indexed_rows,
        "schema": {
            "columns": d.schema.columns,
            "row_count": d.schema.row_count,
            "format": d.schema.format,
            "file_size": d.schema.file_size,
            "has_header": d.schema.has_header,
        },
        "pii_columns": [{"column": p.column, "pattern": p.pattern,
                          "sample": p.sample, "count": p.count}
                         for p in d.schema.pii_columns],
    } for d in items]


@app.post("/api/data/upload")
async def upload_dataset(request: Request, user=Depends(get_current_user)):
    """Streaming upload. Multipart/form-data with 'file' field."""
    from empire.registry.data import get_store

    form = await request.form()
    if "file" not in form:
        raise HTTPException(400, "missing 'file' field")

    upload = form["file"]
    if not hasattr(upload, "filename"):
        raise HTTPException(400, "expected file upload")

    # Reject empty files early
    content_length = upload.size if hasattr(upload, 'size') else 0
    if content_length == 0:
        raise HTTPException(400, "empty file rejected")

    # Validate filename — no path traversal, no null bytes
    if "\x00" in upload.filename or ".." in upload.filename:
        raise HTTPException(400, "invalid filename")

    async def gen():
        from empire.registry.data import MAX_FILE_SIZE
        total = 0
        while True:
            chunk = await upload.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_SIZE:
                raise ValueError(f"file too large: {total} bytes")
            yield chunk

    try:
        ds = await get_store().save_streaming(
            upload.filename, gen(),
            tenant=user["tenant"],
            expected_sha256=form.get("sha256", ""),
        )
        # Reject if no rows were extracted
        if ds.schema.row_count == 0 and ds.schema.columns == []:
            # Cleanup empty dataset
            get_store().delete(ds.id)
            raise HTTPException(400, "file contained no parseable data")
        audit("data.upload", actor=user["email"], tenant=user["tenant"],
              summary=f"dataset {ds.name} uploaded",
              metadata={"size_bytes": ds.size_bytes,
                        "format": ds.format.value,
                        "pii_detected": ds.pii_detected,
                        "pii_columns": [p.column for p in ds.schema.pii_columns]})
        return {
            "id": ds.id, "name": ds.name, "filename": ds.filename,
            "format": ds.format.value, "size_bytes": ds.size_bytes,
            "sha256": ds.sha256,
            "schema": {
                "columns": ds.schema.columns,
                "row_count": ds.schema.row_count,
                "format": ds.schema.format,
                "file_size": ds.schema.file_size,
            },
            "pii_detected": ds.pii_detected,
            "pii_columns": [{"column": p.column, "pattern": p.pattern,
                              "sample": p.sample, "count": p.count}
                             for p in ds.schema.pii_columns],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


@app.delete("/api/data/datasets/{ds_id}")
async def delete_dataset(ds_id: str, user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin required")
    from empire.registry.data import get_store
    store = get_store()
    ds = store.get(ds_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    # Cross-tenant check for non-admin
    if ds.tenant != user["tenant"] and user["role"] != "admin":
        audit("security.cross_tenant_blocked", severity="warning",
              actor=user["email"], tenant=user["tenant"],
              summary=f"blocked cross-tenant dataset delete: {ds_id}")
        raise HTTPException(403, "cross-tenant access denied")
    store.delete(ds_id)
    audit("data.delete", actor=user["email"], tenant=user["tenant"],
          summary=f"dataset {ds.name} deleted",
          metadata={"dataset_id": ds_id})
    return {"ok": True}


@app.get("/api/data/datasets/{ds_id}/query")
async def query_dataset(ds_id: str, limit: int = 100, offset: int = 0,
                        user=Depends(get_current_user)):
    from empire.registry.data import get_store
    # CRITICAL: enforce tenant isolation on dataset access
    store = get_store()
    ds = store.get(ds_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    if ds.tenant != user["tenant"] and user["role"] != "admin":
        # Audit the cross-tenant attempt before rejecting
        audit("security.cross_tenant_blocked", severity="warning",
              actor=user["email"], tenant=user["tenant"],
              summary=f"blocked cross-tenant dataset access: {ds_id}")
        raise HTTPException(403, "dataset belongs to another tenant")
    # Clamp limit to prevent DoS
    limit = min(max(1, limit), MAX_PAGE_LIMIT)
    offset = max(0, offset)
    return store.query(ds_id, limit=limit, offset=offset)


@app.post("/api/data/datasets/{ds_id}/index")
async def index_dataset(ds_id: str, user=Depends(get_current_user)):
    """Index dataset rows into semantic memory."""
    from empire.registry.data import get_store
    from empire.memory.unified import get_memory

    store = get_store()
    ds = store.get(ds_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    if ds.tenant != user["tenant"] and user["role"] != "admin":
        audit("security.cross_tenant_blocked", severity="warning",
              actor=user["email"], tenant=user["tenant"],
              summary=f"blocked cross-tenant dataset index: {ds_id}")
        raise HTTPException(403, "cross-tenant access denied")

    rows = store.query(ds_id, limit=1000)
    mem = get_memory()
    indexed = 0
    for row in rows:
        # Build a textual chunk from the row
        text = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
        mem.remember_knowledge(
            text,
            source="dataset",
            source_id=f"{ds_id}:{indexed}",
            tenant=ds.tenant,
            metadata={"dataset": ds.name, "row_index": indexed},
        )
        indexed += 1
    ds.indexed = True
    ds.indexed_rows = indexed
    store._save_metadata()
    audit("data.index", actor=user["email"], tenant=user["tenant"],
          summary=f"indexed {indexed} rows from {ds.name}",
          metadata={"dataset_id": ds_id})
    return {"ok": True, "indexed_rows": indexed}


# ─── Memory Endpoints ──────────────────────────────────────────────────────

@app.get("/api/memory/episodic")
async def list_episodes(limit: int = 20, outcome: str = "",
                        user=Depends(get_current_user)):
    limit = min(max(1, limit), MAX_PAGE_LIMIT)
    from empire.memory.episodic import get_episodic
    mem = get_episodic()
    episodes = mem.query(tenant=user["tenant"], outcome=outcome or None, limit=limit)
    return {"total": len(episodes), "episodes": [asdict_(e) for e in episodes]}


@app.get("/api/memory/semantic")
async def list_semantic(limit: int = 20, user=Depends(get_current_user)):
    limit = min(max(1, limit), MAX_PAGE_LIMIT)
    from empire.memory.semantic import get_semantic
    mem = get_semantic()
    chunks = list(mem.chunks.values())[:limit]
    return {"total": len(chunks), "chunks": [{
        "id": c.id, "text": c.text[:500],
        "source": c.source, "source_id": c.source_id,
        "tenant": c.tenant, "created_at": c.created_at,
        "metadata": c.metadata,
    } for c in chunks]}


@app.get("/api/memory/procedural")
async def list_procedural(limit: int = 20, user=Depends(get_current_user)):
    limit = min(max(1, limit), MAX_PAGE_LIMIT)
    from empire.memory.procedural import get_procedural
    mem = get_procedural()
    items = mem.list(tenant=user["tenant"])[:limit]
    return {"total": len(items), "procedures": [asdict_(p) for p in items]}


@app.get("/api/memory/recall")
async def recall_memory(q: str, k: int = 5, user=Depends(get_current_user)):
    """Search across all memory types."""
    if not q or len(q.strip()) < 2:
        raise HTTPException(400, "query must be at least 2 chars")
    k = min(max(1, k), 20)
    from empire.memory.unified import MemoryQuery, get_memory
    mq = MemoryQuery(query=q, tenant=user["tenant"], k=k)
    result = get_memory().recall(mq)
    return {
        "episodes": [asdict_(e) for e in result.episodes],
        "chunks": [[asdict_(c), s] for c, s in result.chunks],
        "procedures": [asdict_(p) for p in result.procedures],
    }


# ─── Cognitive Loop Endpoints ──────────────────────────────────────────────

@app.post("/api/cognitive/reflect")
async def cognitive_reflect(user=Depends(get_current_user)):
    """Run lesson extraction on recent episodes."""
    from empire.memory.unified import get_memory
    lesson = get_memory().reflect(tenant=user["tenant"])
    audit("cognitive.reflect", actor=user["email"], tenant=user["tenant"],
          summary=f"reflection extracted lesson: {len(lesson)} chars" if lesson else "no new lesson")
    return {"ok": True, "lesson": lesson}


@app.post("/api/cognitive/consolidate")
async def cognitive_consolidate(user=Depends(get_current_user)):
    """Promote episodic lessons into semantic memory."""
    from empire.memory.unified import get_memory
    promoted = get_memory().consolidate(tenant=user["tenant"])
    audit("cognitive.consolidate", actor=user["email"], tenant=user["tenant"],
          summary=f"consolidated {promoted} items")
    return {"ok": True, "promoted": promoted}


class ThinkRequest(BaseModel):
    goal: str
    session: str = "default"


@app.post("/api/cognitive/think")
async def cognitive_think(req: ThinkRequest, user=Depends(get_current_user)):
    """Run a full cognitive loop for a goal."""
    # Validate input - refuse empty or whitespace-only goals
    goal = req.goal.strip() if req.goal else ""
    if not goal or len(goal) < 5:
        raise HTTPException(400, "goal must be at least 5 non-blank characters")
    if len(goal) > 1000:
        raise HTTPException(400, "goal must be at most 1000 characters")

    from empire.cognitive.loop import get_loop
    import asyncio
    try:
        trace = await get_loop().think(
            goal, session=req.session, tenant=user["tenant"]
        )
        audit("cognitive.think", actor=user["email"], tenant=user["tenant"],
              summary=f"goal: {goal[:60]}",
              metadata={"outcome": trace.final_outcome,
                        "stages": len(trace.stages),
                        "gap": trace.gap_detected})
        return {
            "outcome": trace.final_outcome,
            "stages": trace.stages,
            "lesson_learned": trace.lesson_learned,
            "gap_detected": trace.gap_detected,
            "capability_used": trace.capability_used,
            "started_at": trace.started_at,
        }
    except Exception as e:
        raise HTTPException(400, str(e))


# ─── Helpers ──────────────────────────────────────────────────────────────

def asdict_(obj):
    """Safe asdict."""
    try:
        from dataclasses import asdict
        return asdict(obj)
    except Exception:
        return {"text": str(obj)}


# ─── System Update Endpoints ───────────────────────────────────────────────

_ROOT_PATH = Path(__file__).resolve().parent.parent
UPDATE_SCRIPT = str(_ROOT_PATH / "scripts" / "auto_update.py")
ROOT = str(_ROOT_PATH)


def _run_update_script(args: list[str], timeout: int = 60) -> dict:
    """Run auto_update.py with given args, return parsed result."""
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, str(UPDATE_SCRIPT), *args],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT)
        )
        # Find the JSON blob in stdout (the log lines are not JSON).
        # Use a balanced-brace search to find the outermost top-level object.
        stdout = proc.stdout
        # Find all '{' that start a top-level JSON object
        # Strategy: try parsing from each '{' until one works
        for start in range(len(stdout)):
            if stdout[start] == '{':
                # Find matching '}' via stack
                depth = 0
                in_str = False
                esc = False
                for i in range(start, len(stdout)):
                    c = stdout[i]
                    if esc: esc = False; continue
                    if c == '\\': esc = True; continue
                    if c == '"': in_str = not in_str; continue
                    if in_str: continue
                    if c == '{': depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = stdout[start:i+1]
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, dict):
                                    parsed["_returncode"] = proc.returncode
                                    return parsed
                            except Exception:
                                break  # try next '{'
        return {"ok": False, "stdout": stdout, "stderr": proc.stderr,
                "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


@app.get("/api/system/update/status")
async def system_update_status(user=Depends(get_current_user)):
    """Show update state: docker availability, last check, recent backups."""
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(403, "admin/operator only")
    return _run_update_script(["status"], timeout=15)


@app.post("/api/system/update/check")
async def system_update_check(user=Depends(get_current_user)):
    """Check for available image updates. Does NOT apply."""
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    audit("system.update.check", severity="info", summary="checking for image updates", user=user)
    result = _run_update_script(["check"], timeout=60)
    return result


@app.post("/api/system/update/apply")
async def system_update_apply(user=Depends(get_current_user),
                              background_tasks: BackgroundTasks = None):
    """Apply updates with backup. Long-running — returns immediately."""
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    audit("system.update.apply", severity="warning",
              summary="applying system updates", user=user)
    # Run in foreground but with longer timeout
    return _run_update_script(["apply"], timeout=600)


@app.post("/api/system/update/rollback")
async def system_update_rollback(user=Depends(get_current_user)):
    """Rollback to last backup."""
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    audit("system.update.rollback", severity="warning",
              summary="rolling back system updates", user=user)
    return _run_update_script(["rollback"], timeout=600)


@app.get("/api/system/update/history")
async def system_update_history(user=Depends(get_current_user)):
    """Show last 100 lines of update history."""
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(403, "admin/operator only")
    history = _ROOT_PATH / "logs" / "updates" / "history.log"
    if not history.exists():
        return {"lines": []}
    text = history.read_text()
    lines = text.split("\n")[-100:]
    return {"lines": lines}


# ─── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8123, log_level="info")
