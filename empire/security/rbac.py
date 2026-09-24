"""
Role-based access control for tools and actions.

Combines Role hierarchy with per-action scopes. Use as:
    from empire.security.rbac import require_permission, Permission

    @app.post("/crews/leads", dependencies=[Depends(require_permission(Permission.RUN_LEADS))])
    async def run_leads(...): ...

Or in the agent loop:
    from empire.security.rbac import has_permission
    if not has_permission(auth, Permission.PUBLISH_SOCIAL):
        return "permission denied"
"""
import enum
from typing import Callable

from .auth import AuthContext, Role


class Permission(str, enum.Enum):
    # Read-only
    READ_HISTORY  = "read:history"
    READ_LEADS    = "read:leads"
    READ_AUDIT    = "read:audit"
    VIEW_DASHBOARD = "view:dashboard"

    # Tool execution
    RUN_TESTS     = "run:tests"
    RUN_LEADS     = "run:leads"
    SEND_OUTREACH = "send:outreach"
    PUBLISH_SOCIAL = "publish:social"
    NAVIGATE_BROWSER = "navigate:browser"
    WATCH_VIDEO   = "watch:video"

    # Generators
    GENERATE_IMAGE = "generate:image"
    GENERATE_VIDEO = "generate:video"

    # Health
    CHECK_HEALTH  = "check:health"

    # Admin
    MANAGE_USERS  = "manage:users"
    MANAGE_KEYS   = "manage:keys"
    MANAGE_TENANTS = "manage:tenants"
    VIEW_SECRETS  = "view:secrets"


# Default permissions by role.
# Override via SCOPE claim in JWT (set in issue_token).
DEFAULT_SCOPES: dict[Role, list[Permission]] = {
    Role.ADMIN:    list(Permission),                # everything
    Role.OPERATOR: [                                # can run agent
        Permission.READ_HISTORY, Permission.READ_LEADS, Permission.READ_AUDIT,
        Permission.RUN_TESTS, Permission.RUN_LEADS, Permission.SEND_OUTREACH,
        Permission.NAVIGATE_BROWSER, Permission.WATCH_VIDEO,
        Permission.GENERATE_IMAGE, Permission.GENERATE_VIDEO,
        Permission.CHECK_HEALTH,
    ],
    Role.VIEWER:   [                                # read-only
        Permission.READ_HISTORY, Permission.READ_LEADS, Permission.READ_AUDIT,
        Permission.VIEW_DASHBOARD,
    ],
    Role.AGENT:    [                                # service-to-service
        Permission.RUN_LEADS, Permission.SEND_OUTREACH,
        Permission.PUBLISH_SOCIAL, Permission.NAVIGATE_BROWSER,
        Permission.GENERATE_IMAGE, Permission.GENERATE_VIDEO,
    ],
}


def has_permission(auth: AuthContext, perm: Permission) -> bool:
    """Check if the auth context grants a specific permission."""
    if auth.role == Role.ADMIN:
        return True
    # Token scope takes precedence over role defaults
    if auth.scope:
        # If scope is explicit, treat it as the allowed set
        return perm.value in auth.scope or "*" in auth.scope
    # Otherwise use role defaults
    return perm in DEFAULT_SCOPES.get(auth.role, [])


def require_permission(perm: Permission) -> Callable:
    """
    FastAPI dependency factory. Use:
        @app.post("/foo", dependencies=[Depends(require_permission(Permission.RUN_TESTS))])
    """
    from fastapi import Depends, HTTPException, Request, status

    def _check(request: Request) -> AuthContext:
        # Pull auth from request state (set by AuthMiddleware) OR re-verify
        auth = getattr(request.state, "auth", None)
        if auth is None:
            # Fall back to header check
            from .auth import require_auth as _ra
            auth = _ra(request)
        if not has_permission(auth, perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role '{auth.role}' lacks permission '{perm.value}'",
            )
        return auth
    return _check
