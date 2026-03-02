from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.deps import require_tenant, require_analyst, CurrentUser
from app.models.business_profile import BusinessProfile
from app.models.campaign import Campaign

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str
    google_customer_id: Optional[str] = None


class CampaignDraft(BaseModel):
    campaign_name: str
    campaign_type: str
    objective: str
    budget_micros: int
    bidding_strategy: str
    locations: List[str] = []
    schedule: Dict[str, Any] = {}
    ad_groups: List[Dict[str, Any]] = []
    settings: Dict[str, Any] = {}


class ApproveLaunchRequest(BaseModel):
    draft_campaign_id: str


@router.post("/generate")
async def generate_campaign(
    req: PromptRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete business profile setup first")

    from app.services.campaign_generator import CampaignGeneratorService
    generator = CampaignGeneratorService(db, user.tenant_id)
    draft = await generator.generate_from_prompt(
        prompt=req.prompt,
        business_profile=profile,
        google_customer_id=req.google_customer_id,
    )

    return draft


@router.get("/context")
async def get_prompt_context(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {"profile": None, "existing_campaigns": []}

    campaigns_result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).limit(20)
    )
    campaigns = campaigns_result.scalars().all()

    return {
        "profile": {
            "website": profile.website_url,
            "industry": profile.industry_classification,
            "services": profile.services_json,
            "locations": profile.locations_json,
            "phone": profile.phone,
            "conversion_goal": profile.primary_conversion_goal,
            "offers": profile.offers_json,
            "brand_voice": profile.brand_voice_json,
        },
        "existing_campaigns": [
            {"id": c.id, "name": c.name, "type": c.type, "status": c.status}
            for c in campaigns
        ],
    }


@router.post("/save-draft")
async def save_draft(
    draft: CampaignDraft,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    from app.models.integration_google_ads import IntegrationGoogleAds
    acct_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        ).limit(1)
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="No active Google Ads account")

    campaign = Campaign(
        tenant_id=user.tenant_id,
        google_customer_id=account.customer_id,
        type=draft.campaign_type,
        name=draft.campaign_name,
        status="DRAFT",
        objective=draft.objective,
        budget_micros=draft.budget_micros,
        bidding_strategy=draft.bidding_strategy,
        settings_json={
            "locations": draft.locations,
            "schedule": draft.schedule,
            "ad_groups": draft.ad_groups,
            **draft.settings,
        },
        is_draft=True,
    )
    db.add(campaign)
    await db.flush()

    return {"id": campaign.id, "status": "draft_saved"}


@router.post("/approve-launch")
async def approve_and_launch(
    req: ApproveLaunchRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can launch campaigns")

    result = await db.execute(
        select(Campaign).where(
            Campaign.id == req.draft_campaign_id,
            Campaign.tenant_id == user.tenant_id,
            Campaign.is_draft == True,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Draft campaign not found")

    from app.jobs.tasks import launch_campaign_task
    launch_campaign_task.delay(user.tenant_id, campaign.id, user.user_id)

    campaign.status = "LAUNCHING"
    await db.flush()

    return {"id": campaign.id, "status": "launching"}
