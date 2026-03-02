from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.tenant import Tenant

router = APIRouter()


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    timezone: Optional[str] = None
    autonomy_mode: Optional[str] = None
    risk_tolerance: Optional[str] = None
    daily_budget_cap_micros: Optional[int] = None
    weekly_change_cap_pct: Optional[int] = None


# NOTE: POST /api/tenants (create) is now in workspace.py with full multi-workspace support
# (slug, tenant_settings, audit logging, token issuance)


@router.get("/current")
async def get_current_tenant(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "id": tenant.id,
        "name": tenant.name,
        "industry": tenant.industry,
        "timezone": tenant.timezone,
        "autonomy_mode": tenant.autonomy_mode,
        "risk_tolerance": tenant.risk_tolerance,
        "daily_budget_cap_micros": tenant.daily_budget_cap_micros,
        "weekly_change_cap_pct": tenant.weekly_change_cap_pct,
        "tier": tenant.tier,
    }


@router.patch("/current")
async def update_current_tenant(
    req: UpdateTenantRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can update tenant")

    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)

    await db.flush()
    return {"status": "updated"}
