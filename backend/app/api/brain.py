"""
Jarvis Brain S2S Router — /api/v1/brain/*

Server-to-server endpoints consumed by Jarvis Brain's GoogleAdsConnector.
Auth: X-API-Key header.  Tenant: X-Tenant-Id header (UUID).

Every endpoint here maps 1-to-1 with a method in
jarvis/brain-api/app/services/connectors/google_ads.py
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.campaign import Campaign
from app.models.ad_group import AdGroup
from app.models.keyword import Keyword
from app.models.conversion import Conversion
from app.models.performance_daily import PerformanceDaily
from app.models.search_term_performance import SearchTermPerformance

router = APIRouter()

# ── S2S Auth ──────────────────────────────────────────────────

def _require_brain_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> str:
    expected = getattr(settings, "BRAIN_API_KEY", "") or os.getenv("BRAIN_API_KEY", "")
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brain API key not configured")
    if x_api_key != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return x_api_key


def _tenant_id(x_tenant_id: str = Header(..., alias="X-Tenant-Id")) -> str:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant-Id required")
    return x_tenant_id


def _date_range(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    start = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=30)
    end = date.fromisoformat(date_to) if date_to else date.today()
    return start, end


# ── Helpers ───────────────────────────────────────────────────

def _perf_row(row, impressions, clicks, cost_micros, conversions, conv_value=0.0):
    cost = round(cost_micros / 1_000_000, 2) if cost_micros else 0.0
    return {
        "impressions": impressions,
        "clicks": clicks,
        "cost_micros": cost_micros,
        "cost": cost,
        "conversions": round(conversions, 2),
        "conv_value": round(conv_value, 2),
        "ctr": round((clicks / impressions * 100), 2) if impressions else 0.0,
        "cpc": round(cost / clicks, 2) if clicks else 0.0,
        "cpa": round(cost / conversions, 2) if conversions else 0.0,
    }


# ── Health ────────────────────────────────────────────────────

@router.get("/health")
async def brain_health(
    _key: str = Depends(_require_brain_key),
    db: AsyncSession = Depends(get_db),
):
    return {"status": "ok", "service": "google_ads"}


# ══════════════════════════════════════════════════════════════
# CAMPAIGNS
# ══════════════════════════════════════════════════════════════

@router.get("/campaigns")
async def brain_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Campaign).where(Campaign.tenant_id == tenant_id)
    if status_filter:
        q = q.where(Campaign.status == status_filter)
    q = q.order_by(desc(Campaign.updated_at))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": c.id,
            "campaign_id": c.campaign_id,
            "name": c.name,
            "type": c.type,
            "status": c.status,
            "budget_micros": c.budget_micros or 0,
            "budget": round((c.budget_micros or 0) / 1_000_000, 2),
            "bidding_strategy": c.bidding_strategy,
        }
        for c in rows
    ]


@router.get("/campaigns/performance")
async def brain_campaign_performance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    # Get campaigns
    cq = select(Campaign).where(Campaign.tenant_id == tenant_id)
    if campaign_id:
        cq = cq.where(Campaign.id == campaign_id)
    campaigns = (await db.execute(cq)).scalars().all()

    result = []
    for c in campaigns:
        entity_key = c.campaign_id or c.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("imp"),
                func.sum(PerformanceDaily.clicks).label("cli"),
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
                func.sum(PerformanceDaily.conv_value).label("val"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "campaign",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                    PerformanceDaily.date <= end,
                )
            )
        )
        r = perf.one_or_none()
        imp = int(r.imp or 0) if r else 0
        cli = int(r.cli or 0) if r else 0
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        val = float(r.val or 0) if r else 0.0
        metrics = _perf_row(r, imp, cli, cost_m, conv, val)
        result.append({
            "campaign_id": c.id,
            "google_campaign_id": c.campaign_id,
            "name": c.name,
            "type": c.type,
            "status": c.status,
            **metrics,
        })
    return result


@router.get("/campaigns/roi")
async def brain_campaign_roi(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    cq = select(Campaign).where(Campaign.tenant_id == tenant_id)
    campaigns = (await db.execute(cq)).scalars().all()

    result = []
    for c in campaigns:
        entity_key = c.campaign_id or c.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
                func.sum(PerformanceDaily.conv_value).label("val"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "campaign",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                    PerformanceDaily.date <= end,
                )
            )
        )
        r = perf.one_or_none()
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        val = float(r.val or 0) if r else 0.0
        cost = round(cost_m / 1_000_000, 2) if cost_m else 0.0
        roas = round(val / cost, 2) if cost > 0 else 0.0
        result.append({
            "campaign_id": c.id,
            "name": c.name,
            "cost": cost,
            "conversions": round(conv, 2),
            "conv_value": round(val, 2),
            "roas": roas,
        })
    return result


# ══════════════════════════════════════════════════════════════
# AD GROUPS
# ══════════════════════════════════════════════════════════════

@router.get("/adgroups/performance")
async def brain_adgroup_performance(
    campaign_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    aq = select(AdGroup).where(AdGroup.tenant_id == tenant_id)
    if campaign_id:
        aq = aq.where(AdGroup.campaign_id == campaign_id)
    ad_groups = (await db.execute(aq)).scalars().all()

    result = []
    for ag in ad_groups:
        entity_key = ag.ad_group_id or ag.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("imp"),
                func.sum(PerformanceDaily.clicks).label("cli"),
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "ad_group",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                    PerformanceDaily.date <= end,
                )
            )
        )
        r = perf.one_or_none()
        imp = int(r.imp or 0) if r else 0
        cli = int(r.cli or 0) if r else 0
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        metrics = _perf_row(r, imp, cli, cost_m, conv)
        result.append({
            "ad_group_id": ag.id,
            "name": ag.name,
            "campaign_id": ag.campaign_id,
            "status": ag.status,
            **metrics,
        })
    return result


# ══════════════════════════════════════════════════════════════
# KEYWORDS
# ══════════════════════════════════════════════════════════════

@router.get("/keywords/performance")
async def brain_keyword_performance(
    campaign_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_cost: Optional[float] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    kq = select(Keyword).where(Keyword.tenant_id == tenant_id)
    if campaign_id:
        kq = kq.join(AdGroup, Keyword.ad_group_id == AdGroup.id).where(AdGroup.campaign_id == campaign_id)
    keywords = (await db.execute(kq)).scalars().all()

    result = []
    for kw in keywords:
        entity_key = kw.keyword_id or kw.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("imp"),
                func.sum(PerformanceDaily.clicks).label("cli"),
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "keyword",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                    PerformanceDaily.date <= end,
                )
            )
        )
        r = perf.one_or_none()
        imp = int(r.imp or 0) if r else 0
        cli = int(r.cli or 0) if r else 0
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        cost_dollars = round(cost_m / 1_000_000, 2)
        if min_cost is not None and cost_dollars < min_cost:
            continue
        metrics = _perf_row(r, imp, cli, cost_m, conv)
        result.append({
            "keyword_id": kw.id,
            "google_keyword_id": kw.keyword_id,
            "text": kw.text,
            "match_type": kw.match_type,
            "status": kw.status,
            "quality_score": kw.quality_score,
            "cpc_bid_micros": kw.cpc_bid_micros,
            "ad_group_id": kw.ad_group_id,
            **metrics,
        })
    return result


@router.get("/keywords/quality")
async def brain_keyword_quality(
    campaign_id: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    kq = select(Keyword).where(Keyword.tenant_id == tenant_id)
    if campaign_id:
        kq = kq.join(AdGroup, Keyword.ad_group_id == AdGroup.id).where(AdGroup.campaign_id == campaign_id)
    keywords = (await db.execute(kq)).scalars().all()
    return [
        {
            "keyword_id": kw.id,
            "text": kw.text,
            "match_type": kw.match_type,
            "quality_score": kw.quality_score,
            "status": kw.status,
        }
        for kw in keywords
        if kw.quality_score is not None
    ]


@router.get("/keywords/bid-recommendations")
async def brain_bid_recommendations(
    campaign_id: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start = date.today() - timedelta(days=30)
    kq = select(Keyword).where(Keyword.tenant_id == tenant_id, Keyword.status == "ENABLED")
    if campaign_id:
        kq = kq.join(AdGroup, Keyword.ad_group_id == AdGroup.id).where(AdGroup.campaign_id == campaign_id)
    keywords = (await db.execute(kq)).scalars().all()

    recs = []
    for kw in keywords:
        entity_key = kw.keyword_id or kw.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.clicks).label("cli"),
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "keyword",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                )
            )
        )
        r = perf.one_or_none()
        cli = int(r.cli or 0) if r else 0
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        if cli == 0:
            continue
        actual_cpc = cost_m / cli
        target_cpc = (cost_m / conv) * 0.7 if conv > 0 else actual_cpc * 0.9
        recs.append({
            "keyword_id": kw.id,
            "text": kw.text,
            "current_bid_micros": kw.cpc_bid_micros,
            "recommended_bid_micros": int(target_cpc),
            "reason": "high_cpa" if conv > 0 and (cost_m / conv) > actual_cpc * 1.5 else "optimization",
        })
    return recs


@router.get("/keywords/pause-recommendations")
async def brain_pause_recommendations(
    min_spend: float = Query(20.0),
    max_conversions: int = Query(0),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start = date.today() - timedelta(days=30)
    kq = select(Keyword).where(Keyword.tenant_id == tenant_id, Keyword.status == "ENABLED")
    keywords = (await db.execute(kq)).scalars().all()

    recs = []
    for kw in keywords:
        entity_key = kw.keyword_id or kw.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "keyword",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                )
            )
        )
        r = perf.one_or_none()
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        cost_dollars = round(cost_m / 1_000_000, 2)
        if cost_dollars >= min_spend and conv <= max_conversions:
            recs.append({
                "keyword_id": kw.id,
                "text": kw.text,
                "cost": cost_dollars,
                "conversions": conv,
                "reason": f"${cost_dollars} spent with {conv} conversions in 30d",
            })
    return sorted(recs, key=lambda x: x["cost"], reverse=True)


# ── Write: Pause Keyword ─────────────────────────────────────

@router.post("/keywords/{keyword_id}/pause")
async def brain_pause_keyword(
    keyword_id: str,
    body: dict = None,
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Keyword).where(Keyword.id == keyword_id, Keyword.tenant_id == tenant_id)
    )
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(404, "Keyword not found")
    kw.status = "PAUSED"
    await db.flush()
    return {"status": "paused", "keyword_id": keyword_id, "reason": (body or {}).get("reason")}


# ── Write: Update Keyword Bid ────────────────────────────────

@router.post("/keywords/{keyword_id}/bid")
async def brain_update_bid(
    keyword_id: str,
    body: dict = None,
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    body = body or {}
    result = await db.execute(
        select(Keyword).where(Keyword.id == keyword_id, Keyword.tenant_id == tenant_id)
    )
    kw = result.scalar_one_or_none()
    if not kw:
        raise HTTPException(404, "Keyword not found")
    new_bid = body.get("bid_micros")
    if new_bid is None:
        raise HTTPException(400, "bid_micros required")
    old_bid = kw.cpc_bid_micros
    kw.cpc_bid_micros = int(new_bid)
    await db.flush()
    return {
        "status": "updated",
        "keyword_id": keyword_id,
        "old_bid_micros": old_bid,
        "new_bid_micros": int(new_bid),
    }


# ══════════════════════════════════════════════════════════════
# SEARCH TERMS
# ══════════════════════════════════════════════════════════════

@router.get("/searchterms")
async def brain_search_terms(
    campaign_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    q = select(SearchTermPerformance).where(
        SearchTermPerformance.tenant_id == tenant_id,
        SearchTermPerformance.date >= start,
        SearchTermPerformance.date <= end,
    )
    if campaign_id:
        q = q.where(SearchTermPerformance.campaign_id == campaign_id)
    q = q.order_by(desc(SearchTermPerformance.cost_micros)).limit(500)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "search_term": r.search_term,
            "keyword_text": r.keyword_text,
            "campaign_id": r.campaign_id,
            "ad_group_id": r.ad_group_id,
            "impressions": r.impressions,
            "clicks": r.clicks,
            "cost_micros": r.cost_micros,
            "cost": round(r.cost_micros / 1_000_000, 2) if r.cost_micros else 0,
            "conversions": r.conversions,
            "ctr": r.ctr,
        }
        for r in rows
    ]


@router.get("/searchterms/waste")
async def brain_search_term_waste(
    date_from: Optional[str] = Query(None),
    min_cost: float = Query(10.0),
    max_conversions: int = Query(0),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=30)
    min_cost_micros = int(min_cost * 1_000_000)
    q = (
        select(
            SearchTermPerformance.search_term,
            SearchTermPerformance.keyword_text,
            SearchTermPerformance.campaign_id,
            func.sum(SearchTermPerformance.impressions).label("imp"),
            func.sum(SearchTermPerformance.clicks).label("cli"),
            func.sum(SearchTermPerformance.cost_micros).label("cost"),
            func.sum(SearchTermPerformance.conversions).label("conv"),
        )
        .where(
            SearchTermPerformance.tenant_id == tenant_id,
            SearchTermPerformance.date >= start,
        )
        .group_by(
            SearchTermPerformance.search_term,
            SearchTermPerformance.keyword_text,
            SearchTermPerformance.campaign_id,
        )
        .having(
            and_(
                func.sum(SearchTermPerformance.cost_micros) >= min_cost_micros,
                func.sum(SearchTermPerformance.conversions) <= max_conversions,
            )
        )
        .order_by(desc("cost"))
        .limit(200)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "search_term": r.search_term,
            "keyword_text": r.keyword_text,
            "campaign_id": r.campaign_id,
            "impressions": int(r.imp or 0),
            "clicks": int(r.cli or 0),
            "cost_micros": int(r.cost or 0),
            "cost": round(int(r.cost or 0) / 1_000_000, 2),
            "conversions": float(r.conv or 0),
            "wasted": True,
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════
# CONVERSIONS
# ══════════════════════════════════════════════════════════════

@router.get("/conversions")
async def brain_conversions(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Conversion).where(Conversion.tenant_id == tenant_id)
    if action:
        q = q.where(Conversion.type == action)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "status": c.status,
            "is_primary": c.is_primary,
            "action_id": c.action_id,
        }
        for c in rows
    ]


@router.get("/conversions/calls")
async def brain_call_conversions(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(Conversion).where(
        Conversion.tenant_id == tenant_id,
        Conversion.type == "PHONE_CALL",
    )
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "status": c.status,
            "is_primary": c.is_primary,
        }
        for c in rows
    ]


@router.get("/conversions/lag")
async def brain_conversion_lag(
    date_from: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    # Conversion lag approximated from daily performance data
    start = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=30)
    q = (
        select(
            PerformanceDaily.date,
            func.sum(PerformanceDaily.conversions).label("conv"),
            func.sum(PerformanceDaily.clicks).label("cli"),
        )
        .where(
            PerformanceDaily.tenant_id == tenant_id,
            PerformanceDaily.entity_type == "campaign",
            PerformanceDaily.date >= start,
        )
        .group_by(PerformanceDaily.date)
        .order_by(PerformanceDaily.date)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "date": r.date.isoformat(),
            "conversions": float(r.conv or 0),
            "clicks": int(r.cli or 0),
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════
# COST & ROI
# ══════════════════════════════════════════════════════════════

@router.get("/cost/summary")
async def brain_cost_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    perf = await db.execute(
        select(
            func.sum(PerformanceDaily.impressions).label("imp"),
            func.sum(PerformanceDaily.clicks).label("cli"),
            func.sum(PerformanceDaily.cost_micros).label("cost"),
            func.sum(PerformanceDaily.conversions).label("conv"),
            func.sum(PerformanceDaily.conv_value).label("val"),
        ).where(
            PerformanceDaily.tenant_id == tenant_id,
            PerformanceDaily.entity_type == "campaign",
            PerformanceDaily.date >= start,
            PerformanceDaily.date <= end,
        )
    )
    r = perf.one_or_none()
    imp = int(r.imp or 0) if r else 0
    cli = int(r.cli or 0) if r else 0
    cost_m = int(r.cost or 0) if r else 0
    conv = float(r.conv or 0) if r else 0.0
    val = float(r.val or 0) if r else 0.0
    cost = round(cost_m / 1_000_000, 2)
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "impressions": imp,
        "clicks": cli,
        "cost_micros": cost_m,
        "cost": cost,
        "conversions": round(conv, 2),
        "conv_value": round(val, 2),
        "ctr": round((cli / imp * 100), 2) if imp else 0,
        "cpc": round(cost / cli, 2) if cli else 0,
        "cpa": round(cost / conv, 2) if conv else 0,
        "roas": round(val / cost, 2) if cost else 0,
    }


# ══════════════════════════════════════════════════════════════
# BUDGETS
# ══════════════════════════════════════════════════════════════

@router.get("/budgets")
async def brain_budgets(
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start = date.today() - timedelta(days=7)
    cq = select(Campaign).where(Campaign.tenant_id == tenant_id, Campaign.status == "ENABLED")
    campaigns = (await db.execute(cq)).scalars().all()

    result = []
    for c in campaigns:
        entity_key = c.campaign_id or c.id
        perf = await db.execute(
            select(func.sum(PerformanceDaily.cost_micros).label("cost")).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "campaign",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                )
            )
        )
        r = perf.one_or_none()
        spent_7d = int(r.cost or 0) if r else 0
        budget = c.budget_micros or 0
        utilization = round((spent_7d / 7) / budget * 100, 1) if budget else 0
        result.append({
            "campaign_id": c.id,
            "name": c.name,
            "daily_budget_micros": budget,
            "daily_budget": round(budget / 1_000_000, 2),
            "avg_daily_spend_7d": round(spent_7d / 7 / 1_000_000, 2),
            "utilization_pct": utilization,
        })
    return result


@router.get("/budgets/recommendations")
async def brain_budget_recommendations(
    date_from: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=14)
    cq = select(Campaign).where(Campaign.tenant_id == tenant_id, Campaign.status == "ENABLED")
    campaigns = (await db.execute(cq)).scalars().all()

    recs = []
    for c in campaigns:
        entity_key = c.campaign_id or c.id
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conv"),
                func.count().label("days"),
            ).where(
                and_(
                    PerformanceDaily.tenant_id == tenant_id,
                    PerformanceDaily.entity_type == "campaign",
                    PerformanceDaily.entity_id == entity_key,
                    PerformanceDaily.date >= start,
                )
            )
        )
        r = perf.one_or_none()
        cost_m = int(r.cost or 0) if r else 0
        conv = float(r.conv or 0) if r else 0.0
        days = int(r.days or 1) if r else 1
        budget = c.budget_micros or 0
        avg_spend = cost_m / days if days > 0 else 0
        if budget > 0 and avg_spend / budget < 0.7 and conv > 0:
            recs.append({
                "campaign_id": c.id,
                "name": c.name,
                "current_budget_micros": budget,
                "recommended_budget_micros": int(avg_spend * 1.2),
                "reason": "under_spending_with_conversions",
            })
        elif budget > 0 and conv == 0 and cost_m > 0:
            recs.append({
                "campaign_id": c.id,
                "name": c.name,
                "current_budget_micros": budget,
                "recommended_budget_micros": int(budget * 0.5),
                "reason": "no_conversions_reduce_budget",
            })
    return recs


# ── Write: Update Campaign Budget ────────────────────────────

@router.post("/campaigns/{campaign_id}/budget")
async def brain_update_budget(
    campaign_id: str,
    body: dict = None,
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    body = body or {}
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    new_budget = body.get("budget_micros")
    if new_budget is None:
        raise HTTPException(400, "budget_micros required")
    old_budget = campaign.budget_micros
    campaign.budget_micros = int(new_budget)
    await db.flush()
    return {
        "status": "updated",
        "campaign_id": campaign_id,
        "old_budget_micros": old_budget,
        "new_budget_micros": int(new_budget),
    }


# ══════════════════════════════════════════════════════════════
# LOCATIONS & CATEGORIES
# ══════════════════════════════════════════════════════════════

@router.get("/locations/performance")
async def brain_location_performance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    q = (
        select(
            PerformanceDaily.entity_id,
            func.sum(PerformanceDaily.impressions).label("imp"),
            func.sum(PerformanceDaily.clicks).label("cli"),
            func.sum(PerformanceDaily.cost_micros).label("cost"),
            func.sum(PerformanceDaily.conversions).label("conv"),
        )
        .where(
            PerformanceDaily.tenant_id == tenant_id,
            PerformanceDaily.entity_type == "location",
            PerformanceDaily.date >= start,
            PerformanceDaily.date <= end,
        )
        .group_by(PerformanceDaily.entity_id)
        .order_by(desc("cost"))
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "location_id": r.entity_id,
            "impressions": int(r.imp or 0),
            "clicks": int(r.cli or 0),
            "cost": round(int(r.cost or 0) / 1_000_000, 2),
            "conversions": float(r.conv or 0),
        }
        for r in rows
    ]


@router.get("/categories/performance")
async def brain_category_performance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    # Categories inferred from campaign names/types
    start, end = _date_range(date_from, date_to)
    q = (
        select(
            Campaign.type,
            func.sum(PerformanceDaily.impressions).label("imp"),
            func.sum(PerformanceDaily.clicks).label("cli"),
            func.sum(PerformanceDaily.cost_micros).label("cost"),
            func.sum(PerformanceDaily.conversions).label("conv"),
        )
        .join(
            PerformanceDaily,
            and_(
                PerformanceDaily.entity_id == Campaign.campaign_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.tenant_id == tenant_id,
            ),
        )
        .where(
            Campaign.tenant_id == tenant_id,
            PerformanceDaily.date >= start,
            PerformanceDaily.date <= end,
        )
        .group_by(Campaign.type)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "category": r.type,
            "impressions": int(r.imp or 0),
            "clicks": int(r.cli or 0),
            "cost": round(int(r.cost or 0) / 1_000_000, 2),
            "conversions": float(r.conv or 0),
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════
# QUALITY TRENDS & WASTE DETECTION
# ══════════════════════════════════════════════════════════════

@router.get("/quality/trends")
async def brain_quality_trends(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    kq = select(Keyword).where(
        Keyword.tenant_id == tenant_id,
        Keyword.quality_score.isnot(None),
    )
    keywords = (await db.execute(kq)).scalars().all()
    if not keywords:
        return {"average_quality_score": None, "distribution": {}}
    scores = [kw.quality_score for kw in keywords]
    dist = {}
    for s in scores:
        dist[str(s)] = dist.get(str(s), 0) + 1
    return {
        "average_quality_score": round(sum(scores) / len(scores), 2),
        "total_keywords": len(scores),
        "distribution": dist,
        "below_5_count": sum(1 for s in scores if s < 5),
    }


@router.get("/waste/high-spend-low-booking")
async def brain_waste_high_spend(
    min_spend: float = Query(50.0),
    date_from: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=30)
    min_cost_micros = int(min_spend * 1_000_000)
    q = (
        select(
            PerformanceDaily.entity_id,
            func.sum(PerformanceDaily.impressions).label("imp"),
            func.sum(PerformanceDaily.clicks).label("cli"),
            func.sum(PerformanceDaily.cost_micros).label("cost"),
            func.sum(PerformanceDaily.conversions).label("conv"),
        )
        .where(
            PerformanceDaily.tenant_id == tenant_id,
            PerformanceDaily.entity_type == "campaign",
            PerformanceDaily.date >= start,
        )
        .group_by(PerformanceDaily.entity_id)
        .having(
            and_(
                func.sum(PerformanceDaily.cost_micros) >= min_cost_micros,
                func.sum(PerformanceDaily.conversions) <= 1,
            )
        )
        .order_by(desc("cost"))
    )
    rows = (await db.execute(q)).all()
    # Resolve campaign names
    result = []
    for r in rows:
        cq = await db.execute(
            select(Campaign.name).where(
                Campaign.tenant_id == tenant_id,
                (Campaign.campaign_id == r.entity_id) | (Campaign.id == r.entity_id),
            )
        )
        name = cq.scalar_one_or_none() or r.entity_id
        result.append({
            "entity_id": r.entity_id,
            "campaign_name": name,
            "impressions": int(r.imp or 0),
            "clicks": int(r.cli or 0),
            "cost": round(int(r.cost or 0) / 1_000_000, 2),
            "conversions": float(r.conv or 0),
            "wasted": True,
        })
    return result


# ══════════════════════════════════════════════════════════════
# LEAD ATTRIBUTION
# ══════════════════════════════════════════════════════════════

@router.get("/leads/attribution")
async def brain_lead_attribution(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    _key: str = Depends(_require_brain_key),
    tenant_id: str = Depends(_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    start, end = _date_range(date_from, date_to)
    q = (
        select(
            Campaign.id,
            Campaign.name,
            Campaign.type,
            func.sum(PerformanceDaily.clicks).label("cli"),
            func.sum(PerformanceDaily.cost_micros).label("cost"),
            func.sum(PerformanceDaily.conversions).label("conv"),
            func.sum(PerformanceDaily.conv_value).label("val"),
        )
        .join(
            PerformanceDaily,
            and_(
                PerformanceDaily.entity_id == Campaign.campaign_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.tenant_id == tenant_id,
            ),
        )
        .where(
            Campaign.tenant_id == tenant_id,
            PerformanceDaily.date >= start,
            PerformanceDaily.date <= end,
        )
        .group_by(Campaign.id, Campaign.name, Campaign.type)
        .order_by(desc("conv"))
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "campaign_id": r.id,
            "campaign_name": r.name,
            "campaign_type": r.type,
            "clicks": int(r.cli or 0),
            "cost": round(int(r.cost or 0) / 1_000_000, 2),
            "leads": float(r.conv or 0),
            "lead_value": round(float(r.val or 0), 2),
            "cost_per_lead": round(int(r.cost or 0) / 1_000_000 / float(r.conv), 2) if r.conv else 0,
        }
        for r in rows
    ]
