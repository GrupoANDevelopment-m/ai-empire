"""
empire.security — auth, RBAC, rate limiting, PII redaction.

This is the single security gate between the world and the agent. Every
HTTP request that touches the LangGraph API, the agent REPL, or any
tool execution goes through these checks.

  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ request  │ ─▶ │  JWT     │ ─▶ │  RBAC    │ ─▶ │  rate    │
  │          │    │ verify   │    │ check    │    │  limit   │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │ PII redact   │
                                              │ + audit log  │
                                              └──────────────┘
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │   agent /    │
                                              │   tool call  │
                                              └──────────────┘

Used by:
- orchestrator/main.py (FastAPI dependency)
- empire/agent/llm/agent.py (per-tool rate + audit)
- web/server.py (UI auth)
"""
from .auth import AuthContext, require_auth, issue_token, verify_token, Role
from .rbac import Permission, require_permission
from .rate_limit import RateLimiter, RateLimitExceeded
from .pii import PIIRedactor, redact
from .audit import AuditLogger, audit_log

__all__ = [
    "AuthContext", "require_auth", "issue_token", "verify_token", "Role",
    "Permission", "require_permission",
    "RateLimiter", "RateLimitExceeded",
    "PIIRedactor", "redact",
    "AuditLogger", "audit_log",
]
