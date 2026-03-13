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

    return {
        "id": campaign.id,
        "name": campaign.name,
        "type": campaign.type,
        "status": campaign.status,
        "objective": campaign.objective,
        "budget": campaign.budget_micros / 1_000_000 if campaign.budget_micros else 0,
        "bidding_strategy": campaign.bidding_strategy,
        "settings": campaign.settings_json,
        "is_draft": campaign.is_draft,
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
    }


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
