"""
Multi-Workspace API Routes
/api/me, /api/me/active-tenant, /api/tenants CRUD, invitations, members, audit
"""
import uuid
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.core.deps import (
    get_current_user, require_tenant, require_permission,
    CurrentUser, get_client_info,
)
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
from app.models.user_session import UserSession
from app.models.invitation import Invitation
from app.models.audit_event import AuditEvent
from app.models.tenant_settings import TenantSettings
from app.services.audit_service import log_event

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────

class MeResponse(BaseModel):
    user: dict
    active_tenant_id: Optional[str] = None
    tenants: list


class SetActiveTenantRequest(BaseModel):
    tenant_id: str


class CreateTenantRequest(BaseModel):
    name: str
    industry: Optional[str] = None
    timezone: str = "America/Chicago"
    website: Optional[str] = None


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "viewer"


class AcceptInviteRequest(BaseModel):
    token: str
    full_name: Optional[str] = None
    password: Optional[str] = None


class ChangeRoleRequest(BaseModel):
    role: str


# ── /api/me ──────────────────────────────────────────────

@router.get("/me")
async def get_me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enhanced /api/me — returns user info, active tenant, and all accessible tenants."""
    result = await db.execute(select(User).where(User.id == user.user_id))
    u = result.scalars().first()
    if not u:
        raise HTTPException(404, "User not found")

    # Get all tenants
    tu_result = await db.execute(
        select(TenantUser, Tenant)
        .join(Tenant, TenantUser.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user.user_id)
    )
    rows = tu_result.all()
    tenants = [
        {"id": t.id, "name": t.name, "role": tu.role, "industry": t.industry, "tier": t.tier, "slug": t.slug}
        for tu, t in rows
    ]

    # Get active tenant from user_session
    sess_result = await db.execute(select(UserSession).where(UserSession.user_id == user.user_id))
    session = sess_result.scalars().first()
    active_tenant_id = session.active_tenant_id if session else user.tenant_id

    return {
        "user": {"id": u.id, "email": u.email, "full_name": u.full_name},
        "active_tenant_id": active_tenant_id,
        "tenants": tenants,
    }


@router.post("/me/active-tenant")
async def set_active_tenant(
    req: SetActiveTenantRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set active workspace. Validates membership then issues tenant-scoped tokens."""
    # Validate membership
    tu_result = await db.execute(
        select(TenantUser).where(
            and_(TenantUser.user_id == user.user_id, TenantUser.tenant_id == req.tenant_id)
        )
    )
    tu = tu_result.scalars().first()
    if not tu:
        raise HTTPException(403, "You do not have access to this workspace.")

    # Upsert user_session
    sess_result = await db.execute(select(UserSession).where(UserSession.user_id == user.user_id))
    session = sess_result.scalars().first()
    old_tenant_id = session.active_tenant_id if session else None

    if session:
        session.active_tenant_id = req.tenant_id
        session.last_tenant_switch_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)
    else:
        session = UserSession(
            id=str(uuid.uuid4()),
            user_id=user.user_id,
            active_tenant_id=req.tenant_id,
            last_tenant_switch_at=datetime.now(timezone.utc),
        )
        db.add(session)

    # Audit log
    client = get_client_info(request)
    await log_event(
        db, "TENANT_SWITCH", severity="info",
        tenant_id=req.tenant_id, user_id=user.user_id,
        metadata={"from_tenant_id": old_tenant_id, "to_tenant_id": req.tenant_id},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )

    # Issue new tenant-scoped tokens
    access_token = create_access_token(user_id=user.user_id, tenant_id=req.tenant_id, role=tu.role)
    refresh_token = create_refresh_token(user_id=user.user_id)

    return {
        "ok": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "tenant_id": req.tenant_id,
        "role": tu.role,
    }


# ── /api/tenants ──────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants the current user can access."""
    result = await db.execute(
        select(TenantUser, Tenant)
        .join(Tenant, TenantUser.tenant_id == Tenant.id)
        .where(TenantUser.user_id == user.user_id)
    )
    rows = result.all()
    return [
        {"id": t.id, "name": t.name, "role": tu.role, "industry": t.industry, "tier": t.tier, "slug": t.slug}
        for tu, t in rows
    ]


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] + "-" + secrets.token_hex(3) if slug else secrets.token_hex(6)


@router.post("/tenants")
async def create_tenant(
    req: CreateTenantRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tenant. Current user becomes owner."""
    tenant = Tenant(
        id=str(uuid.uuid4()),
        name=req.name,
        industry=req.industry,
        timezone=req.timezone,
        slug=_slugify(req.name),
    )
    db.add(tenant)
    await db.flush()

    # Add owner role
    tu = TenantUser(
        id=str(uuid.uuid4()),
        tenant_id=tenant.id,
        user_id=user.user_id,
        role="owner",
    )
    db.add(tu)

    # Create tenant_settings
    ts = TenantSettings(tenant_id=tenant.id)
    db.add(ts)

    # Set as active tenant
    sess_result = await db.execute(select(UserSession).where(UserSession.user_id == user.user_id))
    session = sess_result.scalars().first()
    if session:
        session.active_tenant_id = tenant.id
        session.last_tenant_switch_at = datetime.now(timezone.utc)
    else:
        session = UserSession(
            id=str(uuid.uuid4()),
            user_id=user.user_id,
            active_tenant_id=tenant.id,
            last_tenant_switch_at=datetime.now(timezone.utc),
        )
        db.add(session)

    # Audit
    client = get_client_info(request)
    await log_event(
        db, "TENANT_CREATED", severity="info",
        tenant_id=tenant.id, user_id=user.user_id,
        metadata={"name": req.name, "industry": req.industry},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )

    # Issue tokens
    access_token = create_access_token(user_id=user.user_id, tenant_id=tenant.id, role="owner")
    refresh_token = create_refresh_token(user_id=user.user_id)

    return {
        "ok": True,
        "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


# ── Invitations ──────────────────────────────────────────

@router.post("/tenants/{tenant_id}/invite")
async def invite_to_tenant(
    tenant_id: str,
    req: InviteRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("members.invite")),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user by email to join a tenant."""
    if req.role not in ("owner", "admin", "analyst", "viewer"):
        raise HTTPException(400, "Invalid role")

    # Check if already a member
    existing_user = await db.execute(select(User).where(User.email == req.email))
    eu = existing_user.scalars().first()
    if eu:
        existing_tu = await db.execute(
            select(TenantUser).where(
                and_(TenantUser.user_id == eu.id, TenantUser.tenant_id == tenant_id)
            )
        )
        if existing_tu.scalars().first():
            raise HTTPException(409, "User is already a member of this workspace")

    # Check for existing pending invite
    existing_inv = await db.execute(
        select(Invitation).where(
            and_(
                Invitation.tenant_id == tenant_id,
                Invitation.email == req.email,
                Invitation.status == "pending",
            )
        )
    )
    if existing_inv.scalars().first():
        raise HTTPException(409, "A pending invitation already exists for this email")

    invite = Invitation(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        email=req.email,
        role=req.role,
        invited_by_user_id=user.user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)

    client = get_client_info(request)
    await log_event(
        db, "INVITE_SENT", severity="info",
        tenant_id=tenant_id, user_id=user.user_id,
        metadata={"email": req.email, "role": req.role, "invite_id": invite.id},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )

    return {"ok": True, "invite_id": invite.id, "status": "pending", "token": invite.token}


@router.post("/invitations/accept")
async def accept_invitation(
    req: AcceptInviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Accept an invitation. If user doesn't exist, create account. If logged in, link to existing."""
    result = await db.execute(select(Invitation).where(Invitation.token == req.token))
    invite = result.scalars().first()
    if not invite:
        raise HTTPException(404, "Invalid invitation token")
    if invite.status != "pending":
        raise HTTPException(400, f"Invitation is {invite.status}")
    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = "expired"
        raise HTTPException(400, "Invitation has expired")

    # Find or create user
    user_result = await db.execute(select(User).where(User.email == invite.email))
    user = user_result.scalars().first()

    if not user:
        if not req.password:
            raise HTTPException(400, "Password required for new account")
        user = User(
            id=str(uuid.uuid4()),
            email=invite.email,
            full_name=req.full_name or "",
            password_hash=hash_password(req.password),
        )
        db.add(user)
        await db.flush()

    # Check not already a member
    existing = await db.execute(
        select(TenantUser).where(
            and_(TenantUser.user_id == user.id, TenantUser.tenant_id == invite.tenant_id)
        )
    )
    if existing.scalars().first():
        invite.status = "accepted"
        return {"ok": True, "tenant_id": invite.tenant_id, "role": invite.role, "message": "Already a member"}

    # Create membership
    tu = TenantUser(
        id=str(uuid.uuid4()),
        tenant_id=invite.tenant_id,
        user_id=user.id,
        role=invite.role,
    )
    db.add(tu)

    invite.status = "accepted"
    invite.updated_at = datetime.now(timezone.utc)

    # Set active tenant for new user
    sess_result = await db.execute(select(UserSession).where(UserSession.user_id == user.id))
    session = sess_result.scalars().first()
    if session:
        session.active_tenant_id = invite.tenant_id
    else:
        db.add(UserSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            active_tenant_id=invite.tenant_id,
        ))

    client = get_client_info(request)
    await log_event(
        db, "INVITE_ACCEPTED", severity="info",
        tenant_id=invite.tenant_id, user_id=user.id,
        metadata={"email": invite.email, "role": invite.role},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )

    access_token = create_access_token(user_id=user.id, tenant_id=invite.tenant_id, role=invite.role)
    refresh_token = create_refresh_token(user_id=user.id)

    return {
        "ok": True,
        "tenant_id": invite.tenant_id,
        "role": invite.role,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.get("/tenants/{tenant_id}/invitations")
async def list_invitations(
    tenant_id: str,
    user: CurrentUser = Depends(require_permission("members.list")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invitation).where(Invitation.tenant_id == tenant_id).order_by(Invitation.created_at.desc())
    )
    invites = result.scalars().all()
    return [
        {
            "id": i.id, "email": i.email, "role": i.role, "status": i.status,
            "expires_at": i.expires_at.isoformat(), "created_at": i.created_at.isoformat(),
        }
        for i in invites
    ]


@router.post("/tenants/{tenant_id}/invitations/{invite_id}/revoke")
async def revoke_invitation(
    tenant_id: str,
    invite_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("members.invite")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invitation).where(
            and_(Invitation.id == invite_id, Invitation.tenant_id == tenant_id, Invitation.status == "pending")
        )
    )
    invite = result.scalars().first()
    if not invite:
        raise HTTPException(404, "Invitation not found or already processed")
    invite.status = "revoked"
    invite.updated_at = datetime.now(timezone.utc)

    client = get_client_info(request)
    await log_event(
        db, "INVITE_REVOKED", severity="info",
        tenant_id=tenant_id, user_id=user.user_id,
        metadata={"invite_id": invite_id, "email": invite.email},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )
    return {"ok": True}


# ── Members ──────────────────────────────────────────────

@router.get("/tenants/{tenant_id}/members")
async def list_members(
    tenant_id: str,
    user: CurrentUser = Depends(require_permission("members.list")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TenantUser, User)
        .join(User, TenantUser.user_id == User.id)
        .where(TenantUser.tenant_id == tenant_id)
    )
    rows = result.all()
    return [
        {
            "user_id": u.id, "email": u.email, "full_name": u.full_name,
            "role": tu.role, "joined_at": tu.created_at.isoformat(),
        }
        for tu, u in rows
    ]


@router.post("/tenants/{tenant_id}/members/{member_user_id}/role")
async def change_member_role(
    tenant_id: str,
    member_user_id: str,
    req: ChangeRoleRequest,
    request: Request,
    user: CurrentUser = Depends(require_permission("members.role_change")),
    db: AsyncSession = Depends(get_db),
):
    if req.role not in ("owner", "admin", "analyst", "viewer"):
        raise HTTPException(400, "Invalid role")

    # Can't change your own role
    if member_user_id == user.user_id:
        raise HTTPException(400, "Cannot change your own role")

    # Only owners can promote to owner
    if req.role == "owner" and user.role != "owner":
        raise HTTPException(403, "Only owners can promote to owner")

    result = await db.execute(
        select(TenantUser).where(
            and_(TenantUser.tenant_id == tenant_id, TenantUser.user_id == member_user_id)
        )
    )
    tu = result.scalars().first()
    if not tu:
        raise HTTPException(404, "Member not found")

    old_role = tu.role
    tu.role = req.role

    client = get_client_info(request)
    await log_event(
        db, "ROLE_CHANGED", severity="warn",
        tenant_id=tenant_id, user_id=user.user_id,
        metadata={"target_user_id": member_user_id, "old_role": old_role, "new_role": req.role},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )
    return {"ok": True}


@router.delete("/tenants/{tenant_id}/members/{member_user_id}")
async def remove_member(
    tenant_id: str,
    member_user_id: str,
    request: Request,
    user: CurrentUser = Depends(require_permission("members.remove")),
    db: AsyncSession = Depends(get_db),
):
    # Can't remove yourself
    if member_user_id == user.user_id:
        raise HTTPException(400, "Cannot remove yourself. Transfer ownership first.")

    result = await db.execute(
        select(TenantUser).where(
            and_(TenantUser.tenant_id == tenant_id, TenantUser.user_id == member_user_id)
        )
    )
    tu = result.scalars().first()
    if not tu:
        raise HTTPException(404, "Member not found")

    # Only owners can remove other owners
    if tu.role == "owner" and user.role != "owner":
        raise HTTPException(403, "Only owners can remove other owners")

    await db.delete(tu)

    client = get_client_info(request)
    await log_event(
        db, "MEMBER_REMOVED", severity="warn",
        tenant_id=tenant_id, user_id=user.user_id,
        metadata={"removed_user_id": member_user_id, "removed_role": tu.role},
        ip_address=client["ip_address"], user_agent=client["user_agent"],
    )
    return {"ok": True}


# ── Audit Log ──────────────────────────────────────────

@router.get("/tenants/{tenant_id}/audit")
async def get_audit_log(
    tenant_id: str,
    limit: int = 50,
    event_type: Optional[str] = None,
    user: CurrentUser = Depends(require_permission("audit.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()
    return [
        {
            "id": e.id, "event_type": e.event_type, "severity": e.severity,
            "user_id": e.user_id, "metadata": e.metadata_json,
            "ip_address": e.ip_address, "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
