"""
JWT auth for the AI Empire agent API.

Uses HS256 with a shared SECRET_KEY. Tokens carry:
  sub  — user id (UUID or string)
  role — one of: admin, operator, viewer, agent
  tenant — tenant id (for multi-tenant setups)
  scope — list of allowed actions
  exp  — expiration timestamp

In production, prefer asymmetric (RS256) with a JWKS endpoint.
"""
import enum
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import jwt
from fastapi import HTTPException, Request, status


class Role(str, enum.Enum):
    """Hierarchy: admin > operator > viewer > agent."""
    ADMIN    = "admin"      # full access, can manage users + keys
    OPERATOR = "operator"   # can run agent, send outreach, post social
    VIEWER   = "viewer"     # read-only: query history, view leads, audit
    AGENT    = "agent"      # service-to-service, no UI access


ROLE_HIERARCHY = {
    Role.ADMIN:    4,
    Role.OPERATOR: 3,
    Role.VIEWER:   2,
    Role.AGENT:    1,
}


def _secret() -> str:
    s = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET")
    if not s or len(s) < 32:
        raise RuntimeError(
            "SECRET_KEY env var must be set to 32+ random characters. "
            "Generate one with: openssl rand -hex 32"
        )
    return s


def issue_token(
    sub: str,
    role: Role = Role.OPERATOR,
    tenant: str = "default",
    scope: list[str] | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """Sign a JWT for the given user/role. ttl defaults to 1h."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role.value,
        "tenant": tenant,
        "scope": scope or [],
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_token(token: str) -> dict:
    """Verify and return payload. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"invalid token: {e}")


@dataclass
class AuthContext:
    """Extracted from JWT in HTTP requests. Available as request.state.auth."""
    sub: str
    role: Role
    tenant: str
    scope: list[str] = field(default_factory=list)
    raw_claims: dict = field(default_factory=dict)

    def has_role(self, required: Role) -> bool:
        return ROLE_HIERARCHY.get(self.role, 0) >= ROLE_HIERARCHY.get(required, 0)

    def has_scope(self, action: str) -> bool:
        # Wildcard: admin gets everything
        if "*" in self.scope or self.role == Role.ADMIN:
            return True
        return action in self.scope


def require_auth(request: Request) -> AuthContext:
    """
    FastAPI dependency. Reads Bearer token from Authorization header,
    verifies it, returns AuthContext. Use as:
        @app.get("/whoami", dependencies=[Depends(require_auth)])
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid Authorization header (expected 'Bearer <jwt>')",
            headers={"WWW-Authenticate": 'Bearer realm="ai-empire"'},
        )
    token = auth_header[7:]
    payload = verify_token(token)
    try:
        role = Role(payload["role"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"unknown role: {payload.get('role')}")
    return AuthContext(
        sub=payload.get("sub", "anonymous"),
        role=role,
        tenant=payload.get("tenant", "default"),
        scope=payload.get("scope", []),
        raw_claims=payload,
    )


def optional_auth(request: Request) -> Optional[AuthContext]:
    """Like require_auth but returns None if no header (for public endpoints)."""
    try:
        return require_auth(request)
    except HTTPException:
        return None
