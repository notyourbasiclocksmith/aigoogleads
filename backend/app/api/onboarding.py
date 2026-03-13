from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.deps import require_tenant, get_current_user, CurrentUser
from app.core.security import create_access_token
from app.models.business_profile import BusinessProfile
from app.models.social_profile import SocialProfile
from app.models.tenant import Tenant
from app.models.tenant_user import TenantUser
import uuid

router = APIRouter()


class Step1Request(BaseModel):
    business_name: Optional[str] = None
    tenant_name: Optional[str] = None
    website_url: Optional[str] = None
    industry: str = ""
    service_area: Optional[Dict[str, Any]] = None
    phone: Optional[str] = None
    primary_conversion_goal: str = "calls"


class Step4Request(BaseModel):
    monthly_budget: int = 1000
    conversion_goal: str = "calls"
    call_tracking_provider: Optional[str] = None
    call_tracking_id: Optional[str] = None


class Step5Request(BaseModel):
    autonomy_mode: str = "suggest"
    risk_tolerance: str = "low"


@router.post("/step1")
async def onboarding_step1(
    req: Step1Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    biz_name = req.business_name or req.tenant_name or "My Business"

    # If user has no tenant yet, create one
    tenant_id = user.tenant_id
    if not tenant_id:
        # Check if user already owns a tenant (registered but no tenant in JWT)
        existing = await db.execute(
            select(TenantUser).where(TenantUser.user_id == user.user_id)
        )
        tu = existing.scalars().first()
        if tu:
            tenant_id = tu.tenant_id
        else:
            # Create new tenant + membership + settings
            from app.models.tenant_settings import TenantSettings
            tenant_id = str(uuid.uuid4())
            tenant = Tenant(id=tenant_id, name=biz_name, industry=req.industry)
            db.add(tenant)
            tu = TenantUser(tenant_id=tenant_id, user_id=user.user_id, role="owner")
            db.add(tu)
            db.add(TenantSettings(tenant_id=tenant_id))
            await db.flush()

    # Update tenant info
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant:
        tenant.name = biz_name
        tenant.industry = req.industry

    # Upsert business profile
    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id))
    profile = result2.scalar_one_or_none()
    if not profile:
        profile = BusinessProfile(tenant_id=tenant_id)
        db.add(profile)

    # Only set website_url if explicitly provided (step2 owns this field)
    if req.website_url:
        profile.website_url = req.website_url
    profile.industry_classification = req.industry
    if req.phone:
        profile.phone = req.phone
    # Don't overwrite conversion goal if already set (step4 owns this field)
    if not profile.primary_conversion_goal:
        profile.primary_conversion_goal = req.primary_conversion_goal
    if req.service_area:
        profile.locations_json = req.service_area

    await db.flush()

    # Issue a tenant-scoped token so subsequent steps work
    access_token = create_access_token(user_id=user.user_id, tenant_id=tenant_id, role="owner")

    return {
        "status": "ok",
        "step": 1,
        "profile_id": profile.id,
        "tenant_id": tenant_id,
        "access_token": access_token,
    }


class Step2Request(BaseModel):
    website_url: Optional[str] = None
    description: Optional[str] = None
    social_links: Any = []
    gbp_link: Optional[str] = None


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

    if req.website_url:
        profile.website_url = req.website_url
    if req.description:
        profile.description = req.description
    profile.gbp_link = req.gbp_link

    # Handle social_links as dict {platform: url} or list [{platform, url}]
    links = req.social_links
    if isinstance(links, dict):
        links = [{"platform": k, "url": v} for k, v in links.items() if v]

    # Remove old social profiles to prevent duplicates on re-submission
    if links:
        from sqlalchemy import delete as sa_delete
        await db.execute(
            sa_delete(SocialProfile).where(SocialProfile.tenant_id == user.tenant_id)
        )

    for link in links:
        platform = link.get("platform", "other")
        url = link.get("url", "")
        if url:
            sp = SocialProfile(tenant_id=user.tenant_id, platform=platform, url=url)
            db.add(sp)

    await db.flush()

    # Trigger async business analysis (website + social crawl + AI)
    from app.jobs.tasks import analyze_business_task
    analyze_business_task.delay(user.tenant_id)

    return {"status": "ok", "step": 2, "analysis_started": True}


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
    # Save budget to tenant
    result_t = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result_t.scalar_one_or_none()
    if tenant:
        tenant.daily_budget_cap_micros = int(req.monthly_budget / 30 * 1_000_000)

    # Save conversion goal + tracking to business profile
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result.scalar_one_or_none()
    if profile:
        profile.primary_conversion_goal = req.conversion_goal
        profile.constraints_json = {
            **(profile.constraints_json or {}),
            "monthly_budget": req.monthly_budget,
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
        tenant.autonomy_mode = req.autonomy_mode
        tenant.risk_tolerance = req.risk_tolerance

    await db.flush()

    # Trigger background scan after onboarding
    from app.jobs.tasks import scan_business_task
    scan_business_task.delay(user.tenant_id)

    return {"status": "ok", "step": 5, "onboarding_complete": True}


@router.get("/data")
async def onboarding_data(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result2.scalar_one_or_none()

    from app.models.integration_google_ads import IntegrationGoogleAds
    acct_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
            IntegrationGoogleAds.customer_id != "pending",
        ).limit(1)
    )
    acct = acct_result.scalar_one_or_none()

    social_result = await db.execute(
        select(SocialProfile).where(SocialProfile.tenant_id == user.tenant_id)
    )
    socials = social_result.scalars().all()
    social_map = {s.platform: s.url for s in socials}

    constraints = (profile.constraints_json or {}) if profile else {}

    return {
        "business_name": tenant.name if tenant else "",
        "industry": tenant.industry if tenant else "",
        "phone": profile.phone if profile else "",
        "website_url": profile.website_url if profile else "",
        "description": profile.description if profile else "",
        "gbp_link": profile.gbp_link if profile else "",
        "facebook_url": social_map.get("facebook", ""),
        "instagram_url": social_map.get("instagram", ""),
        "tiktok_url": social_map.get("tiktok", ""),
        "google_ads_connected": acct is not None,
        "service_area": (profile.locations_json or {}).get("primary", "") if profile else "",
        "monthly_budget": constraints.get("monthly_budget", 1000),
        "conversion_goal": profile.primary_conversion_goal if profile else "calls",
        "autonomy_mode": tenant.autonomy_mode if tenant else "semi_auto",
    }


@router.get("/status")
async def onboarding_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result.scalar_one_or_none()

    result2 = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result2.scalar_one_or_none()

    # Check if social profiles exist (step2 creates them)
    social_count_result = await db.execute(
        select(func.count()).select_from(SocialProfile).where(SocialProfile.tenant_id == user.tenant_id)
    )
    has_socials = (social_count_result.scalar() or 0) > 0

    constraints = (profile.constraints_json or {}) if profile else {}

    steps = {
        "step1": profile is not None and profile.industry_classification is not None,
        "step2": profile is not None and (bool(profile.website_url) or bool(profile.gbp_link) or has_socials),
        "step3": False,
        "step4": profile is not None and bool(constraints.get("monthly_budget")),
        "step5": tenant is not None and tenant.autonomy_mode is not None,
    }

    from app.models.integration_google_ads import IntegrationGoogleAds
    count_result = await db.execute(
        select(func.count()).select_from(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.customer_id != "pending",
        )
    )
    steps["step3"] = (count_result.scalar() or 0) > 0

    return {"steps": steps, "complete": all(steps.values())}


@router.get("/analysis-status")
async def analysis_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id))
    profile = result.scalar_one_or_none()
    if not profile:
        return {"status": "not_started"}

    ai_analysis = (profile.constraints_json or {}).get("ai_analysis", {})
    ai_status = ai_analysis.get("status", "pending")

    return {
        "status": ai_status,
        "completed_at": ai_analysis.get("completed_at"),
        "social_assessment": ai_analysis.get("social_assessment", {}),
        "website_assessment": ai_analysis.get("website_assessment", {}),
        "services": (profile.services_json or {}).get("list", []),
        "brand_voice": profile.brand_voice_json or {},
        "usp": (profile.usp_json or {}).get("list", []),
        "trust_signals": (profile.trust_signals_json or {}).get("list", []),
        "ads_recommendations": (profile.snippets_json or {}).get("ai_recommendations", {}),
        "target_audience": (profile.snippets_json or {}).get("target_audience", {}),
    }
