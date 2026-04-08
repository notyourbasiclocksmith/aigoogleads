"""
Brain API — Meta Ads endpoints for Jarvis S2S calls.
"""
from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_brain_api_key, S2SContext
from app.services.meta_service import MetaService

router = APIRouter(prefix="/meta")


# ── Request Body Models ──────────────────────────────────────

class CreateCampaignRequest(BaseModel):
    name: str
    objective: str = "OUTCOME_LEADS"
    daily_budget: int = 2000
    status: str = "PAUSED"

class CreateAdSetRequest(BaseModel):
    campaign_id: str
    name: str
    daily_budget: int = 2000
    optimization_goal: str = "LEAD_GENERATION"
    targeting: Optional[Dict] = None
    status: str = "PAUSED"

class CreateAdCreativeRequest(BaseModel):
    name: str
    page_id: str
    message: str
    link: Optional[str] = None
    image_url: Optional[str] = None
    call_to_action_type: str = "LEARN_MORE"

class CreateAdRequest(BaseModel):
    name: str
    adset_id: str
    creative_id: str
    status: str = "PAUSED"

class AiCreateAdCreativeRequest(BaseModel):
    page_id: str
    business_name: str = ""
    business_type: str = ""
    topic: str
    link: Optional[str] = None
    cta_type: str = "LEARN_MORE"
    include_image: bool = True


@router.get("/health")
async def meta_health(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.health_check(ctx.tenant_id)


# ── Account ────────────────────────────────────────────────

@router.get("/account")
async def get_account_info(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_account_info(ctx.tenant_id)


# ── Campaigns ──────────────────────────────────────────────

@router.get("/campaigns")
async def get_campaigns(
    status_filter: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_campaigns(ctx.tenant_id, status_filter)


@router.get("/campaigns/{campaign_id}/insights")
async def get_campaign_insights(
    campaign_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_campaign_insights(ctx.tenant_id, campaign_id, date_from, date_to)


@router.get("/campaigns/performance")
async def get_all_performance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_all_performance(ctx.tenant_id, date_from, date_to)


@router.post("/campaigns")
async def create_campaign(
    body: CreateCampaignRequest,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.create_campaign(ctx.tenant_id, body.name, body.objective, body.daily_budget, body.status)


@router.post("/campaigns/{campaign_id}/status")
async def update_campaign_status(
    campaign_id: str,
    status: str = Body(..., embed=True),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.update_campaign_status(ctx.tenant_id, campaign_id, status)


@router.post("/campaigns/{campaign_id}/budget")
async def update_campaign_budget(
    campaign_id: str,
    daily_budget: int = Body(..., embed=True),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.update_campaign_budget(ctx.tenant_id, campaign_id, daily_budget)


# ── Ad Sets ────────────────────────────────────────────────

@router.get("/adsets")
async def get_adsets(
    campaign_id: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_adsets(ctx.tenant_id, campaign_id)


@router.get("/adsets/{adset_id}/insights")
async def get_adset_insights(
    adset_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_adset_insights(ctx.tenant_id, adset_id, date_from, date_to)


@router.post("/adsets")
async def create_adset(
    body: CreateAdSetRequest,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.create_adset(
        ctx.tenant_id, body.campaign_id, body.name, body.daily_budget,
        body.optimization_goal, body.targeting, body.status,
    )


# ── Ads & Creatives ────────────────────────────────────────

@router.get("/ads")
async def get_ads(
    adset_id: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_ads(ctx.tenant_id, adset_id)


@router.get("/ads/{ad_id}/insights")
async def get_ad_insights(
    ad_id: str,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_ad_insights(ctx.tenant_id, ad_id, date_from, date_to)


@router.post("/creatives")
async def create_ad_creative(
    body: CreateAdCreativeRequest,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.create_ad_creative(
        ctx.tenant_id, body.name, body.page_id, body.message, body.link, body.image_url, body.call_to_action_type,
    )


@router.post("/creatives/ai-create")
async def ai_create_ad_creative(
    body: AiCreateAdCreativeRequest,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.ai_create_ad_creative(
        ctx.tenant_id, body.page_id, body.business_name, body.business_type, body.topic,
        body.link, body.cta_type, body.include_image,
    )


@router.post("/ads")
async def create_ad(
    body: CreateAdRequest,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.create_ad(ctx.tenant_id, body.adset_id, body.name, body.creative_id, body.status)


# ── Audiences ──────────────────────────────────────────────

@router.get("/audiences")
async def get_audiences(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.get_audiences(ctx.tenant_id)


# ── Audit / Context ───────────────────────────────────────

@router.get("/context")
async def get_full_context(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.build_full_context(ctx.tenant_id, date_from, date_to)


@router.post("/audit")
async def ai_audit(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaService(db)
    return await svc.ai_audit(ctx.tenant_id)
