from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.core.deps import get_current_user, CurrentUser
from app.models.user import User
from app.models.tenant_user import TenantUser
from app.models.tenant import Tenant

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict
    tenants: list = []


class SelectTenantRequest(BaseModel):
    tenant_id: str


class TenantInfo(BaseModel):
    id: str
    name: str
    role: str
    industry: Optional[str] = None
    tier: str = "starter"


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(user_id=user.id)
    refresh_token = create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": user.id, "email": user.email, "full_name": user.full_name},
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    access_token = create_access_token(user_id=user.id)
    refresh_token = create_refresh_token(user_id=user.id)

    # Fetch user tenants so frontend can auto-select
    tu_result = await db.execute(
        select(TenantUser, Tenant)
        .join(Tenant, TenantUser.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user.id)
    )
    rows = tu_result.all()
    tenants = [
        {"tenant_id": t.id, "name": t.name, "role": tu.role, "industry": t.industry, "tier": t.tier}
        for tu, t in rows
    ]

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": user.id, "email": user.email, "full_name": user.full_name},
        tenants=tenants,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    new_access = create_access_token(user_id=user.id)
    new_refresh = create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user={"id": user.id, "email": user.email, "full_name": user.full_name},
    )


@router.get("/me")
async def get_me(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user.user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "tenant_id": user.tenant_id, "role": user.role}


@router.get("/tenants", response_model=List[TenantInfo])
async def get_user_tenants(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TenantUser, Tenant)
        .join(Tenant, TenantUser.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user.user_id)
    )
    rows = result.all()
    return [
        TenantInfo(id=t.id, name=t.name, role=tu.role, industry=t.industry, tier=t.tier)
        for tu, t in rows
    ]


@router.post("/select-tenant", response_model=TokenResponse)
async def select_tenant(req: SelectTenantRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TenantUser).where(TenantUser.user_id == user.user_id, TenantUser.tenant_id == req.tenant_id)
    )
    tu = result.scalar_one_or_none()
    if not tu:
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    result2 = await db.execute(select(User).where(User.id == user.user_id))
    u = result2.scalar_one_or_none()

    access_token = create_access_token(user_id=user.user_id, tenant_id=req.tenant_id, role=tu.role)
    refresh_token = create_refresh_token(user_id=user.user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={"id": u.id, "email": u.email, "full_name": u.full_name, "tenant_id": req.tenant_id, "role": tu.role},
    )
