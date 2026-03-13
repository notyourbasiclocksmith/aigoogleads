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
from app.models.business_profile import BusinessProfile
from app.models.integration_google_ads import IntegrationGoogleAds

router = APIRouter()


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "viewer"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class UpdateIntegrationRequest(BaseModel):
    integration_type: str
    config: dict = {}


# ── Profile ────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result2.scalar_one_or_none()
    # Check for connected Google Ads account
    acct_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        ).limit(1)
    )
    acct = acct_result.scalar_one_or_none()
    notifications = ((profile.constraints_json or {}).get("notifications", {})) if profile else {}
    return {
        "business_name": tenant.name if tenant else "",
        "industry": tenant.industry if tenant else "",
        "phone": profile.phone if profile else "",
        "website_url": profile.website_url if profile else "",
        "description": profile.description if profile else "",
        "google_ads_customer_id": acct.customer_id if acct else None,
        "notification_email": notifications.get("notification_email", ""),
        "email_alerts": notifications.get("email_alerts", True),
        "weekly_report": notifications.get("weekly_report", True),
        "recommendation_alerts": notifications.get("recommendation_alerts", True),
        "budget_alerts": notifications.get("budget_alerts", True),
    }


class UpdateProfileRequest(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    phone: Optional[str] = None
    website_url: Optional[str] = None
    description: Optional[str] = None
    notification_email: Optional[str] = None
    email_alerts: Optional[bool] = None
    weekly_report: Optional[bool] = None
    recommendation_alerts: Optional[bool] = None
    budget_alerts: Optional[bool] = None


@router.put("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        if req.business_name is not None:
            tenant.name = req.business_name
        if req.industry is not None:
            tenant.industry = req.industry

    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result2.scalar_one_or_none()
    if profile:
        if req.phone is not None:
            profile.phone = req.phone
        if req.website_url is not None:
            profile.website_url = req.website_url
        if req.description is not None:
            profile.description = req.description
        # Persist notification preferences
        notifications = (profile.constraints_json or {}).get("notifications", {})
        if req.notification_email is not None:
            notifications["notification_email"] = req.notification_email
        if req.email_alerts is not None:
            notifications["email_alerts"] = req.email_alerts
        if req.weekly_report is not None:
            notifications["weekly_report"] = req.weekly_report
        if req.recommendation_alerts is not None:
            notifications["recommendation_alerts"] = req.recommendation_alerts
        if req.budget_alerts is not None:
            notifications["budget_alerts"] = req.budget_alerts
        if any(v is not None for v in [req.notification_email, req.email_alerts, req.weekly_report, req.recommendation_alerts, req.budget_alerts]):
            constraints = profile.constraints_json or {}
            constraints["notifications"] = notifications
            profile.constraints_json = constraints

    await db.flush()
    return {"status": "ok"}


# ── Guardrails ─────────────────────────────────────────────────

@router.get("/guardrails")
async def get_guardrails(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return {}
    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result2.scalar_one_or_none()
    constraints = (profile.constraints_json or {}) if profile else {}
    return {
        "autonomy_mode": tenant.autonomy_mode,
        "risk_tolerance": tenant.risk_tolerance,
        "max_daily_budget": round(tenant.daily_budget_cap_micros / 1_000_000, 2) if tenant.daily_budget_cap_micros else None,
        "max_cpc": constraints.get("max_cpc"),
        "max_budget_increase_pct": tenant.weekly_change_cap_pct,
        "min_roas": constraints.get("min_roas"),
    }


class UpdateGuardrailsRequest(BaseModel):
    autonomy_mode: Optional[str] = None
    risk_tolerance: Optional[str] = None
    max_daily_budget: Optional[float] = None
    max_cpc: Optional[float] = None
    max_budget_increase_pct: Optional[int] = None
    min_roas: Optional[float] = None


@router.put("/guardrails")
async def update_guardrails(
    req: UpdateGuardrailsRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        if req.autonomy_mode is not None:
            tenant.autonomy_mode = req.autonomy_mode
        if req.risk_tolerance is not None:
            tenant.risk_tolerance = req.risk_tolerance
        if req.max_daily_budget is not None:
            tenant.daily_budget_cap_micros = int(req.max_daily_budget * 1_000_000)
        if req.max_budget_increase_pct is not None:
            tenant.weekly_change_cap_pct = req.max_budget_increase_pct

    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result2.scalar_one_or_none()
    if profile:
        constraints = profile.constraints_json or {}
        if req.max_cpc is not None:
            constraints["max_cpc"] = req.max_cpc
        if req.min_roas is not None:
            constraints["min_roas"] = req.min_roas
        profile.constraints_json = constraints

    await db.flush()
    return {"status": "ok"}


# ── Team ───────────────────────────────────────────────────────

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


@router.post("/notifications/test")
async def send_test_notification(
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Send a test email to the tenant's notification email address."""
    from app.services.email_service import send_email, get_tenant_notification_prefs

    prefs = await get_tenant_notification_prefs(db, user.tenant_id)
    email = prefs.get("notification_email")
    if not email:
        raise HTTPException(status_code=400, detail="No notification email configured. Save one in Settings first.")

    from app.services.email_service import _wrap_html
    html = _wrap_html(
        "✅ Test Notification",
        '<p style="font-size:15px;color:#334155;">This is a test email from <strong>IgniteAds AI</strong>.</p>'
        '<p style="font-size:14px;color:#64748b;">If you received this, your email notifications are working correctly!</p>'
        '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:12px 16px;margin:12px 0;">'
        '<p style="font-size:13px;color:#15803d;margin:0;">✓ SendGrid connected</p>'
        '<p style="font-size:13px;color:#15803d;margin:4px 0;">✓ Email delivery working</p>'
        '<p style="font-size:13px;color:#15803d;margin:4px 0;">✓ Notification preferences active</p>'
        '</div>',
    )
    result = await send_email(to_email=email, subject="[IgniteAds] Test Notification", html_body=html)
    if result.get("success"):
        return {"status": "sent", "email": email}
    raise HTTPException(status_code=500, detail=result.get("error", "Failed to send"))


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
