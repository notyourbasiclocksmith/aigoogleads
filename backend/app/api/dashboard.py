from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import date, timedelta
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.performance_daily import PerformanceDaily
from app.models.alert import Alert
from app.models.campaign import Campaign

router = APIRouter()


@router.get("/kpis")
async def get_kpis(
    days: int = Query(30, ge=1, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(
            func.sum(PerformanceDaily.impressions).label("impressions"),
            func.sum(PerformanceDaily.clicks).label("clicks"),
            func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
            func.sum(PerformanceDaily.conversions).label("conversions"),
            func.sum(PerformanceDaily.conv_value).label("conv_value"),
        )
        .where(
            and_(
                PerformanceDaily.tenant_id == user.tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.date >= start_date,
            )
        )
    )
    row = result.one_or_none()
    impressions = row.impressions or 0 if row else 0
    clicks = row.clicks or 0 if row else 0
    cost_micros = row.cost_micros or 0 if row else 0
    conversions = row.conversions or 0.0 if row else 0.0
    conv_value = row.conv_value or 0.0 if row else 0.0

    ctr = (clicks / impressions * 100) if impressions > 0 else 0
    cpc = (cost_micros / clicks) if clicks > 0 else 0
    cpa = (cost_micros / conversions) if conversions > 0 else 0
    roas = (conv_value / (cost_micros / 1_000_000)) if cost_micros > 0 else 0

    return {
        "period_days": days,
        "impressions": impressions,
        "clicks": clicks,
        "cost": cost_micros / 1_000_000,
        "cost_micros": cost_micros,
        "conversions": round(conversions, 1),
        "conv_value": round(conv_value, 2),
        "ctr": round(ctr, 2),
        "cpc": round(cpc / 1_000_000, 2),
        "cpa": round(cpa / 1_000_000, 2),
        "roas": round(roas, 2),
    }


@router.get("/trends")
async def get_trends(
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days)
    result = await db.execute(
        select(
            PerformanceDaily.date,
            func.sum(PerformanceDaily.impressions).label("impressions"),
            func.sum(PerformanceDaily.clicks).label("clicks"),
            func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
            func.sum(PerformanceDaily.conversions).label("conversions"),
        )
        .where(
            and_(
                PerformanceDaily.tenant_id == user.tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.date >= start_date,
            )
        )
        .group_by(PerformanceDaily.date)
        .order_by(PerformanceDaily.date)
    )
    rows = result.all()
    return [
        {
            "date": str(r.date),
            "impressions": r.impressions or 0,
            "clicks": r.clicks or 0,
            "cost": (r.cost_micros or 0) / 1_000_000,
            "conversions": round(r.conversions or 0, 1),
        }
        for r in rows
    ]


@router.get("/alerts")
async def get_alerts(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Alert)
        .where(and_(Alert.tenant_id == user.tenant_id, Alert.resolved_at.is_(None)))
        .order_by(desc(Alert.created_at))
        .limit(20)
    )
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "type": a.type,
            "severity": a.severity,
            "message": a.message,
            "entity_ref": a.entity_ref_json,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.get("/campaign-summary")
async def get_campaign_summary(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign.status, func.count().label("count"))
        .where(Campaign.tenant_id == user.tenant_id)
        .group_by(Campaign.status)
    )
    rows = result.all()
    return {r.status: r.count for r in rows}


@router.get("/campaigns")
async def get_dashboard_campaigns(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=30)
    result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).limit(20)
    )
    campaigns = result.scalars().all()

    campaign_data = []
    for c in campaigns:
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
                    PerformanceDaily.entity_id == c.id,
                    PerformanceDaily.date >= start_date,
                )
            )
        )
        row = perf.one_or_none()
        impressions = (row.impressions or 0) if row else 0
        clicks = (row.clicks or 0) if row else 0
        cost_micros = (row.cost_micros or 0) if row else 0
        conversions = (row.conversions or 0) if row else 0

        campaign_data.append({
            "campaign_id": c.id,
            "name": c.name,
            "status": c.status,
            "type": c.type,
            "impressions": impressions,
            "clicks": clicks,
            "cost": round(cost_micros / 1_000_000, 2),
            "conversions": round(conversions, 1),
            "cpa": round((cost_micros / conversions / 1_000_000), 2) if conversions > 0 else 0,
        })
    return campaign_data
