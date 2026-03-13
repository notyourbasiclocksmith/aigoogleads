import json as json_lib
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
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


class SaveDraftRequest(BaseModel):
    draft: Dict[str, Any]


class ApproveLaunchRequest(BaseModel):
    draft_campaign_id: Optional[str] = None
    draft: Optional[Dict[str, Any]] = None


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


@router.post("/generate-stream")
async def generate_campaign_stream(
    req: PromptRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE endpoint that streams step-by-step progress events during campaign generation.
    Each event is a JSON object with: step, status, message, and optional detail.
    The final event has step="complete" with the full draft in detail.
    """
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete business profile setup first")

    from app.services.campaign_generator import CampaignGeneratorService
    generator = CampaignGeneratorService(db, user.tenant_id)

    async def event_stream():
        try:
            async for event in generator.generate_from_prompt_streaming(
                prompt=req.prompt,
                business_profile=profile,
                google_customer_id=req.google_customer_id,
            ):
                data = json_lib.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            error_event = json_lib.dumps({"step": "error", "status": "error", "message": str(e)})
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    req: SaveDraftRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    from app.models.integration_google_ads import IntegrationGoogleAds
    acct_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
            IntegrationGoogleAds.customer_id != "pending",
        ).limit(1)
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="No active Google Ads account")

    d = req.draft
    camp_data = d.get("campaign", {})
    campaign = Campaign(
        tenant_id=user.tenant_id,
        google_customer_id=account.customer_id,
        type=camp_data.get("type", "SEARCH"),
        name=camp_data.get("name", "AI Campaign"),
        status="DRAFT",
        objective=camp_data.get("objective", "leads"),
        budget_micros=camp_data.get("budget_micros", 30_000_000),
        bidding_strategy=camp_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
        settings_json={
            "locations": camp_data.get("locations", []),
            "schedule": camp_data.get("schedule", {}),
            "device_bids": camp_data.get("device_bids", {}),
            "network": camp_data.get("settings", {}).get("network", "SEARCH"),
            "ad_groups": d.get("ad_groups", []),
            "extensions": d.get("extensions", {}),
            "keyword_strategy": d.get("keyword_strategy", {}),
            "reasoning": d.get("reasoning", {}),
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

    campaign = None

    # Case 1: Existing draft in DB
    if req.draft_campaign_id:
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == req.draft_campaign_id,
                Campaign.tenant_id == user.tenant_id,
                Campaign.is_draft == True,
            )
        )
        campaign = result.scalar_one_or_none()

    # Case 2: Inline draft — auto-save then launch
    if not campaign and req.draft:
        from app.models.integration_google_ads import IntegrationGoogleAds
        acct_result = await db.execute(
            select(IntegrationGoogleAds).where(
                IntegrationGoogleAds.tenant_id == user.tenant_id,
                IntegrationGoogleAds.is_active == True,
                IntegrationGoogleAds.customer_id != "pending",
            ).limit(1)
        )
        account = acct_result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=400, detail="No active Google Ads account")

        d = req.draft
        camp_data = d.get("campaign", {})
        campaign = Campaign(
            tenant_id=user.tenant_id,
            google_customer_id=account.customer_id,
            type=camp_data.get("type", "SEARCH"),
            name=camp_data.get("name", "AI Campaign"),
            status="DRAFT",
            objective=camp_data.get("objective", "leads"),
            budget_micros=camp_data.get("budget_micros", 30_000_000),
            bidding_strategy=camp_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
            settings_json={
                "locations": camp_data.get("locations", []),
                "schedule": camp_data.get("schedule", {}),
                "device_bids": camp_data.get("device_bids", {}),
                "network": camp_data.get("settings", {}).get("network", "SEARCH"),
                "ad_groups": d.get("ad_groups", []),
                "extensions": d.get("extensions", {}),
                "keyword_strategy": d.get("keyword_strategy", {}),
                "reasoning": d.get("reasoning", {}),
            },
            is_draft=True,
        )
        db.add(campaign)
        await db.flush()

    if not campaign:
        raise HTTPException(status_code=404, detail="Draft campaign not found — provide draft_campaign_id or inline draft")

    from app.jobs.tasks import launch_campaign_task
    launch_campaign_task.delay(user.tenant_id, campaign.id, user.user_id)

    campaign.status = "LAUNCHING"
    await db.flush()

    return {"id": campaign.id, "status": "launching"}
