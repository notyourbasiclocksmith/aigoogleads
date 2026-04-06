from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.security import decode_token
from app.core.permissions import has_permission
from app.core.config import settings

bearer_scheme = HTTPBearer()


class CurrentUser:
    """Authenticated user context — populated from JWT + optional DB validation."""
    def __init__(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        role: Optional[str] = None,
        verified_membership: bool = False,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role
        self.verified_membership = verified_membership


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    """Decode JWT and return user context. Does NOT validate tenant membership yet."""
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return CurrentUser(
        user_id=user_id,
        tenant_id=payload.get("tenant_id"),
        role=payload.get("role"),
    )


async def require_tenant(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    HARD tenant isolation gate.
    Resolves tenant_id from: URL path param > header > JWT claim.
    Then validates user membership in that tenant via DB lookup.
    """
    from app.models.tenant_user import TenantUser

    # 1. Resolve tenant_id: URL path > header > JWT
    tenant_id = (
        request.path_params.get("tenant_id")
        or request.headers.get("X-Tenant-ID")
        or user.tenant_id
    )
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant selected. Please select a tenant first.",
        )

    # 2. Validate membership via DB (NOT just JWT)
    result = await db.execute(
        select(TenantUser).where(
            and_(TenantUser.user_id == user.user_id, TenantUser.tenant_id == tenant_id)
        )
    )
    tu = result.scalars().first()
    if not tu:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace.",
        )

    # 3. Return enriched user context with DB-verified role
    user.tenant_id = tenant_id
    user.role = tu.role
    user.verified_membership = True
    return user


def require_permission(permission: str):
    """
    Dependency factory: validates user has a specific RBAC permission in their current tenant.
    Must be used AFTER require_tenant.
    """
    async def checker(
        request: Request,
        user: CurrentUser = Depends(require_tenant),
    ) -> CurrentUser:
        if not has_permission(user.role or "", permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' denied for role '{user.role}'.",
            )
        return user
    return checker


def require_role(*allowed_roles: str):
    """Dependency factory: validates user role is in allowed set (DB-verified)."""
    async def role_checker(
        request: Request,
        user: CurrentUser = Depends(require_tenant),
    ) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. Required: {list(allowed_roles)}",
            )
        return user
    return role_checker


async def verify_resource_tenant(resource_tenant_id: Optional[str], user: CurrentUser) -> None:
    """
    Hard check: resource.tenant_id must match the user's active tenant.
    Call this after fetching any entity by ID to prevent cross-tenant access.
    Returns 404 (not 403) to avoid information leakage.
    """
    if resource_tenant_id is None or resource_tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found.",
        )


def get_client_info(request: Request) -> dict:
    """Extract IP and user-agent from request for audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    return {
        "ip_address": ip,
        "user_agent": request.headers.get("User-Agent", "")[:512],
    }


# Convenience aliases (backward compatible)
require_owner = require_role("owner", "admin")
require_analyst = require_role("owner", "admin", "analyst")
require_viewer = require_role("owner", "admin", "analyst", "viewer")


# ── S2S (Service-to-Service) Auth for Brain API ────────────────────
class S2SContext:
    """Context for service-to-service calls (e.g. Jarvis → IntelliAds)."""
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id


async def require_brain_api_key(request: Request) -> S2SContext:
    """
    Validates X-API-Key header against BRAIN_API_KEY.
    Resolves tenant from X-Tenant-Id header.
    Used for machine-to-machine calls (Jarvis brain, external tools).
    """
    api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if not api_key or not settings.BRAIN_API_KEY or api_key != settings.BRAIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    tenant_id = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-Id header required",
        )
    return S2SContext(tenant_id=tenant_id)
