from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, timedelta

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.campaign import Campaign
from app.models.ad_group import AdGroup
from app.models.ad import Ad
from app.models.keyword import Keyword
from app.models.change_log import ChangeLog
from app.models.performance_daily import PerformanceDaily

router = APIRouter()


@router.get("")
async def list_campaigns(
    status: Optional[str] = None,
    type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign).where(Campaign.tenant_id == user.tenant_id)
    if status:
        query = query.where(Campaign.status == status)
    if type:
        query = query.where(Campaign.type == type)
    query = query.order_by(desc(Campaign.updated_at)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    campaigns = result.scalars().all()

    start_date = date.today() - timedelta(days=30)
    campaign_data = []
    for c in campaigns:
        # Join performance data using Google's campaign_id (stored in entity_id)
        entity_key = c.campaign_id or c.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == user.tenant_id,
                    PerformanceDaily.entity_type == "campaign",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start_date,
                )
            )
        )
        row = perf.one_or_none()
        impressions = int(row.impressions or 0) if row else 0
        clicks = int(row.clicks or 0) if row else 0
        cost_micros = float(row.cost_micros or 0) if row else 0.0
        conversions = float(row.conversions or 0) if row else 0.0

        campaign_data.append({
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "status": c.status,
            "objective": c.objective,
            "budget": float(c.budget_micros) / 1_000_000 if c.budget_micros else 0,
            "budget_micros": c.budget_micros,
            "bidding_strategy": c.bidding_strategy,
            "is_draft": c.is_draft,
            "campaign_id": c.campaign_id,
            "impressions": impressions,
            "clicks": clicks,
            "cost": round(cost_micros / 1_000_000, 2),
            "conversions": round(conversions, 1),
            "ctr": round((clicks / impressions * 100), 2) if impressions > 0 else 0,
            "cpa": round((cost_micros / conversions / 1_000_000), 2) if conversions > 0 else 0,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return campaign_data


@router.get("/{campaign_id}")
async def get_campaign_detail(
    campaign_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == user.tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    ad_groups_result = await db.execute(
        select(AdGroup).where(AdGroup.campaign_id == campaign_id, AdGroup.tenant_id == user.tenant_id)
    )
    ad_groups = ad_groups_result.scalars().all()

    ad_group_details = []
    for ag in ad_groups:
        ads_result = await db.execute(
            select(Ad).where(Ad.ad_group_id == ag.id, Ad.tenant_id == user.tenant_id)
        )
        ads = ads_result.scalars().all()

        kws_result = await db.execute(
            select(Keyword).where(Keyword.ad_group_id == ag.id, Keyword.tenant_id == user.tenant_id)
        )
        kws = kws_result.scalars().all()

        ad_group_details.append({
            "id": ag.id,
            "name": ag.name,
            "status": ag.status,
            "ads": [
                {
                    "id": a.id,
                    "type": a.ad_type,
                    "headlines": a.headlines_json,
                    "descriptions": a.descriptions_json,
                    "final_urls": a.final_urls_json,
                    "status": a.status,
                }
                for a in ads
            ],
            "keywords": [
                {
                    "id": k.id,
                    "text": k.text,
                    "match_type": k.match_type,
                    "status": k.status,
                    "quality_score": k.quality_score,
                }
                for k in kws
            ],
        })

    changes_result = await db.execute(
        select(ChangeLog)
        .where(ChangeLog.tenant_id == user.tenant_id, ChangeLog.entity_id == campaign_id)
        .order_by(desc(ChangeLog.applied_at))
        .limit(20)
    )
    changes = changes_result.scalars().all()

    # Performance stats
    entity_key = campaign.campaign_id or campaign.id
    perf_start = date.today() - timedelta(days=30)
    perf = await db.execute(
        select(
            func.sum(PerformanceDaily.impressions).label("impressions"),
            func.sum(PerformanceDaily.clicks).label("clicks"),
            func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
            func.sum(PerformanceDaily.conversions).label("conversions"),
        ).where(
            and_(
                PerformanceDaily.tenant_id == user.tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.entity_id == entity_key,
                PerformanceDaily.date >= perf_start,
            )
        )
    )
    prow = perf.one_or_none()
    impressions = int(prow.impressions or 0) if prow else 0
    clicks = int(prow.clicks or 0) if prow else 0
    cost_micros_total = float(prow.cost_micros or 0) if prow else 0.0
    conversions = float(prow.conversions or 0) if prow else 0.0

    settings = campaign.settings_json or {}

    return {
        "id": campaign.id,
        "campaign_id": campaign.campaign_id,
        "google_customer_id": campaign.google_customer_id,
        "name": campaign.name,
        "type": campaign.type,
        "status": campaign.status,
        "objective": campaign.objective,
        "budget": campaign.budget_micros / 1_000_000 if campaign.budget_micros else 0,
        "budget_micros": campaign.budget_micros or 0,
        "bidding_strategy": campaign.bidding_strategy,
        "target_cpa_micros": settings.get("target_cpa_micros"),
        "target_roas": settings.get("target_roas"),
        "networks": {
            "search": settings.get("search_network", True),
            "display": settings.get("display_network", False),
            "partner": settings.get("partner_network", False),
        },
        "geo_targets": settings.get("geo_targets", []),
        "language_targets": settings.get("language_targets", []),
        "ad_schedule": settings.get("ad_schedule", []),
        "start_date": settings.get("start_date"),
        "end_date": settings.get("end_date"),
        "ad_rotation": settings.get("ad_rotation", "OPTIMIZE"),
        "url_options": {
            "tracking_template": settings.get("tracking_template", ""),
            "final_url_suffix": settings.get("final_url_suffix", ""),
        },
        "negative_keywords": settings.get("negative_keywords", []),
        "settings": settings,
        "is_draft": campaign.is_draft,
        "performance": {
            "impressions": impressions,
            "clicks": clicks,
            "cost": round(cost_micros_total / 1_000_000, 2),
            "conversions": round(conversions, 1),
            "ctr": round((clicks / impressions * 100), 2) if impressions > 0 else 0,
            "cpa": round((cost_micros_total / conversions / 1_000_000), 2) if conversions > 0 else 0,
            "roas": round((conversions / (cost_micros_total / 1_000_000)), 2) if cost_micros_total > 0 else 0,
        },
        "ad_groups": ad_group_details,
        "changes": [
            {
                "id": ch.id,
                "actor_type": ch.actor_type,
                "entity_type": ch.entity_type,
                "reason": ch.reason,
                "applied_at": ch.applied_at.isoformat() if ch.applied_at else None,
            }
            for ch in changes
        ],
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
    }


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    bidding_strategy: Optional[str] = None
    target_cpa: Optional[float] = None
    target_roas: Optional[float] = None
    search_network: Optional[bool] = None
    display_network: Optional[bool] = None
    partner_network: Optional[bool] = None
    geo_targets: Optional[List[str]] = None
    language_targets: Optional[List[str]] = None
    ad_rotation: Optional[str] = None
    tracking_template: Optional[str] = None
    final_url_suffix: Optional[str] = None
    negative_keywords: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    req: CampaignUpdateRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == user.tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    before = {
        "name": campaign.name,
        "status": campaign.status,
        "budget_micros": campaign.budget_micros,
        "bidding_strategy": campaign.bidding_strategy,
    }

    if req.name is not None:
        campaign.name = req.name
    if req.status is not None and req.status in ("ENABLED", "PAUSED"):
        campaign.status = req.status
    if req.budget is not None:
        campaign.budget_micros = int(req.budget * 1_000_000)
    if req.bidding_strategy is not None:
        campaign.bidding_strategy = req.bidding_strategy

    # Update settings_json for advanced fields
    settings = dict(campaign.settings_json or {})
    if req.target_cpa is not None:
        settings["target_cpa_micros"] = int(req.target_cpa * 1_000_000)
    if req.target_roas is not None:
        settings["target_roas"] = req.target_roas
    if req.search_network is not None:
        settings["search_network"] = req.search_network
    if req.display_network is not None:
        settings["display_network"] = req.display_network
    if req.partner_network is not None:
        settings["partner_network"] = req.partner_network
    if req.geo_targets is not None:
        settings["geo_targets"] = req.geo_targets
    if req.language_targets is not None:
        settings["language_targets"] = req.language_targets
    if req.ad_rotation is not None:
        settings["ad_rotation"] = req.ad_rotation
    if req.tracking_template is not None:
        settings["tracking_template"] = req.tracking_template
    if req.final_url_suffix is not None:
        settings["final_url_suffix"] = req.final_url_suffix
    if req.negative_keywords is not None:
        settings["negative_keywords"] = req.negative_keywords
    if req.start_date is not None:
        settings["start_date"] = req.start_date
    if req.end_date is not None:
        settings["end_date"] = req.end_date
    campaign.settings_json = settings

    after = {
        "name": campaign.name,
        "status": campaign.status,
        "budget_micros": campaign.budget_micros,
        "bidding_strategy": campaign.bidding_strategy,
    }

    log = ChangeLog(
        tenant_id=user.tenant_id,
        actor_type="user",
        actor_id=user.user_id,
        google_customer_id=campaign.google_customer_id,
        entity_type="campaign",
        entity_id=campaign_id,
        before_json=before,
        after_json=after,
        reason="Manual campaign update by user",
    )
    db.add(log)
    await db.flush()

    return {"status": "updated", "campaign_id": campaign_id}


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == user.tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    old_status = campaign.status
    campaign.status = "PAUSED"

    log = ChangeLog(
        tenant_id=user.tenant_id,
        actor_type="user",
        actor_id=user.user_id,
        google_customer_id=campaign.google_customer_id,
        entity_type="campaign",
        entity_id=campaign_id,
        before_json={"status": old_status},
        after_json={"status": "PAUSED"},
        reason="Manual pause by user",
    )
    db.add(log)
    await db.flush()

    return {"status": "paused"}


@router.post("/{campaign_id}/enable")
async def enable_campaign(
    campaign_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == user.tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    old_status = campaign.status
    campaign.status = "ENABLED"

    log = ChangeLog(
        tenant_id=user.tenant_id,
        actor_type="user",
        actor_id=user.user_id,
        google_customer_id=campaign.google_customer_id,
        entity_type="campaign",
        entity_id=campaign_id,
        before_json={"status": old_status},
        after_json={"status": "ENABLED"},
        reason="Manual enable by user",
    )
    db.add(log)
    await db.flush()

    return {"status": "enabled"}
