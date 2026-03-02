from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.deps import require_tenant, require_owner, CurrentUser
from app.models.tenant_user import TenantUser
from app.models.user import User
from app.models.tenant import Tenant

router = APIRouter()


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "viewer"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class UpdateIntegrationRequest(BaseModel):
    integration_type: str
    config: dict = {}


@router.get("/team")
async def list_team_members(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TenantUser, User)
        .join(User, TenantUser.user_id == User.id)
        .where(TenantUser.tenant_id == user.tenant_id)
    )
    rows = result.all()
    return [
        {
            "id": tu.id,
            "user_id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": tu.role,
            "created_at": tu.created_at.isoformat() if tu.created_at else None,
        }
        for tu, u in rows
    ]


@router.post("/team/invite")
async def invite_member(
    req: InviteMemberRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    if req.role not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")

    result = await db.execute(select(User).where(User.email == req.email))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found. They must register first.")

    existing = await db.execute(
        select(TenantUser).where(
            and_(TenantUser.tenant_id == user.tenant_id, TenantUser.user_id == target_user.id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already a member")

    tu = TenantUser(tenant_id=user.tenant_id, user_id=target_user.id, role=req.role)
    db.add(tu)
    await db.flush()

    return {"status": "invited", "user_id": target_user.id, "role": req.role}


@router.patch("/team/{member_id}/role")
async def update_member_role(
    member_id: str,
    req: UpdateMemberRoleRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TenantUser).where(
            TenantUser.id == member_id,
            TenantUser.tenant_id == user.tenant_id,
        )
    )
    tu = result.scalar_one_or_none()
    if not tu:
        raise HTTPException(status_code=404, detail="Member not found")
    if tu.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot change owner role")

    tu.role = req.role
    await db.flush()
    return {"status": "updated"}


@router.delete("/team/{member_id}")
async def remove_member(
    member_id: str,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TenantUser).where(
            TenantUser.id == member_id,
            TenantUser.tenant_id == user.tenant_id,
        )
    )
    tu = result.scalar_one_or_none()
    if not tu:
        raise HTTPException(status_code=404, detail="Member not found")
    if tu.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove owner")

    await db.delete(tu)
    await db.flush()
    return {"status": "removed"}


@router.get("/billing")
async def get_billing(
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    return {
        "tier": tenant.tier if tenant else "starter",
        "tiers": {
            "starter": {
                "price": 0,
                "accounts": 1,
                "autonomy": "suggest",
                "reports": "1/month",
                "prompts": 10,
            },
            "pro": {
                "price": 149,
                "accounts": 3,
                "autonomy": "semi_auto",
                "reports": "weekly",
                "prompts": 50,
            },
            "elite": {
                "price": 399,
                "accounts": "unlimited",
                "autonomy": "full_auto",
                "reports": "weekly+monthly",
                "prompts": "unlimited",
            },
        },
    }
