from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.business_profile import BusinessProfile
from app.models.social_profile import SocialProfile
from app.models.tenant import Tenant

router = APIRouter()


class Step1Request(BaseModel):
    business_name: str
    website_url: Optional[str] = None
    industry: str
    service_area: Optional[Dict[str, Any]] = None
    phone: Optional[str] = None
    primary_conversion_goal: str = "calls"


class Step2Request(BaseModel):
    social_links: List[Dict[str, str]] = []
    gbp_link: Optional[str] = None


class Step4Request(BaseModel):
    call_tracking_provider: Optional[str] = None
    call_tracking_id: Optional[str] = None


class Step5Request(BaseModel):
    daily_budget_cap_micros: int = 50_000_000
    autonomy_mode: str = "suggest"
    risk_tolerance: str = "low"


@router.post("/step1")
async def onboarding_step1(
    req: Step1Request,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        tenant.name = req.business_name
        tenant.industry = req.industry

    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result2.scalar_one_or_none()
    if not profile:
        profile = BusinessProfile(tenant_id=user.tenant_id)
        db.add(profile)

    profile.website_url = req.website_url
    profile.industry_classification = req.industry
    profile.phone = req.phone
    profile.primary_conversion_goal = req.primary_conversion_goal
    profile.locations_json = req.service_area or {}

    await db.flush()
    return {"status": "ok", "step": 1, "profile_id": profile.id}


@router.post("/step2")
async def onboarding_step2(
    req: Step2Request,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete step 1 first")

    profile.gbp_link = req.gbp_link

    for link in req.social_links:
        platform = link.get("platform", "other")
        url = link.get("url", "")
        if url:
            sp = SocialProfile(tenant_id=user.tenant_id, platform=platform, url=url)
            db.add(sp)

    await db.flush()
    return {"status": "ok", "step": 2}


@router.post("/step3/google-ads-url")
async def onboarding_step3_get_oauth_url(
    user: CurrentUser = Depends(require_tenant),
):
    from app.integrations.google_ads.oauth import get_oauth_url
    url = get_oauth_url(state=f"{user.tenant_id}:{user.user_id}")
    return {"oauth_url": url}


@router.post("/step4")
async def onboarding_step4(
    req: Step4Request,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result.scalar_one_or_none()
    if profile:
        profile.constraints_json = {
            **(profile.constraints_json or {}),
            "call_tracking_provider": req.call_tracking_provider,
            "call_tracking_id": req.call_tracking_id,
        }
    await db.flush()
    return {"status": "ok", "step": 4}


@router.post("/step5")
async def onboarding_step5(
    req: Step5Request,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        tenant.daily_budget_cap_micros = req.daily_budget_cap_micros
        tenant.autonomy_mode = req.autonomy_mode
        tenant.risk_tolerance = req.risk_tolerance

    await db.flush()

    # Trigger background scan after onboarding
    from app.jobs.tasks import scan_business_task
    scan_business_task.delay(user.tenant_id)

    return {"status": "ok", "step": 5, "onboarding_complete": True}


@router.get("/status")
async def onboarding_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result.scalar_one_or_none()

    result2 = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result2.scalar_one_or_none()

    steps = {
        "step1": profile is not None and profile.industry_classification is not None,
        "step2": profile is not None and (profile.gbp_link is not None or bool(profile.locations_json)),
        "step3": False,
        "step4": True,
        "step5": tenant is not None and tenant.autonomy_mode != "suggest",
    }

    from sqlalchemy import func
    from app.models.integration_google_ads import IntegrationGoogleAds
    count_result = await db.execute(
        select(func.count()).select_from(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == user.tenant_id)
    )
    steps["step3"] = (count_result.scalar() or 0) > 0

    return {"steps": steps, "complete": all(steps.values())}
