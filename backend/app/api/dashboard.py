from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, case, literal
from datetime import date, timedelta
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.performance_daily import PerformanceDaily
from app.models.alert import Alert
from app.models.campaign import Campaign
from app.models.keyword_performance_daily import KeywordPerformanceDaily
from app.models.search_term_performance import SearchTermPerformance
from app.models.ad_performance_daily import AdPerformanceDaily
from app.models.tenant import Tenant

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
    impressions = int(row.impressions or 0) if row else 0
    clicks = int(row.clicks or 0) if row else 0
    cost_micros = float(row.cost_micros or 0) if row else 0.0
    conversions = float(row.conversions or 0) if row else 0.0
    conv_value = float(row.conv_value or 0) if row else 0.0

    ctr = (clicks / impressions * 100) if impressions > 0 else 0
    cpc = (cost_micros / clicks) if clicks > 0 else 0
    cpa = (cost_micros / conversions) if conversions > 0 else 0
    roas = (conv_value / (cost_micros / 1_000_000)) if cost_micros > 0 else 0

    return {
        "period_days": days,
        "impressions": impressions,
        "clicks": clicks,
        "cost": round(cost_micros / 1_000_000, 2),
        "cost_micros": cost_micros,
        "conversions": round(conversions, 1),
        "conv_value": round(conv_value, 2),
        "ctr": round(ctr, 2),
        "cpc": round(cpc / 1_000_000, 2),
        "cpa": round(cpa / 1_000_000, 2),
        "roas": round(roas, 2),
    }


@router.get("/kpis-comparison")
async def get_kpis_comparison(
    days: int = Query(30, ge=1, le=180),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return current period KPIs vs previous period for comparison."""
    end_date = date.today()
    start_current = end_date - timedelta(days=days)
    start_prev = start_current - timedelta(days=days)

    async def _sum_period(start: date, end: date):
        r = await db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
                func.sum(PerformanceDaily.conv_value).label("conv_value"),
            ).where(
                PerformanceDaily.tenant_id == user.tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.date >= start,
                PerformanceDaily.date < end,
            )
        )
        row = r.one_or_none()
        impressions = int(row.impressions or 0) if row else 0
        clicks = int(row.clicks or 0) if row else 0
        cost_micros = float(row.cost_micros or 0) if row else 0.0
        conversions = float(row.conversions or 0) if row else 0.0
        conv_value = float(row.conv_value or 0) if row else 0.0
        cost = cost_micros / 1_000_000
        return {
            "impressions": impressions,
            "clicks": clicks,
            "cost": round(cost, 2),
            "conversions": round(conversions, 1),
            "conv_value": round(conv_value, 2),
            "ctr": round((clicks / impressions * 100) if impressions > 0 else 0, 2),
            "cpc": round((cost / clicks) if clicks > 0 else 0, 2),
            "cpa": round((cost / conversions) if conversions > 0 else 0, 2),
            "roas": round((conv_value / cost) if cost > 0 else 0, 2),
        }

    current = await _sum_period(start_current, end_date + timedelta(days=1))
    previous = await _sum_period(start_prev, start_current)

    def _pct_change(curr: float, prev: float) -> Optional[float]:
        if prev == 0:
            return None
        return round((curr - prev) / prev * 100, 1)

    changes = {}
    for key in current:
        changes[key] = _pct_change(current[key], previous[key])

    return {
        "period_days": days,
        "current": current,
        "previous": previous,
        "changes": changes,
    }


@router.get("/onboarding-status")
async def get_onboarding_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Check what onboarding steps are completed for the getting-started guide."""
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.v2.operator_scan import OperatorScan

    tid = user.tenant_id

    # 1. Google Ads connected?
    acct_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == tid,
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = acct_result.scalar_one_or_none()
    ads_connected = bool(integration and integration.customer_id and integration.customer_id != "pending")
    has_synced = bool(integration and integration.last_sync_at)

    # 2. Has any campaigns?
    camp_count = await db.execute(
        select(func.count()).select_from(Campaign).where(Campaign.tenant_id == tid)
    )
    has_campaigns = (camp_count.scalar() or 0) > 0

    # 3. Has run first scan?
    scan_result = await db.execute(
        select(func.count()).select_from(OperatorScan).where(
            OperatorScan.tenant_id == tid,
            OperatorScan.status == "ready",
        )
    )
    has_scan = (scan_result.scalar() or 0) > 0

    # 4. Has performance data?
    perf_count = await db.execute(
        select(func.count()).select_from(PerformanceDaily).where(
            PerformanceDaily.tenant_id == tid,
        )
    )
    has_data = (perf_count.scalar() or 0) > 0

    steps = [
        {"key": "connect_ads", "label": "Connect Google Ads", "done": ads_connected, "href": "/settings"},
        {"key": "sync_data", "label": "Sync your account data", "done": has_synced, "href": "/settings"},
        {"key": "first_scan", "label": "Run your first AI scan", "done": has_scan, "href": "/operator"},
        {"key": "review", "label": "Review AI recommendations", "done": has_scan, "href": "/operator"},
    ]
    completed = sum(1 for s in steps if s["done"])
    return {
        "steps": steps,
        "completed": completed,
        "total": len(steps),
        "all_done": completed == len(steps),
        "has_data": has_data,
        "has_campaigns": has_campaigns,
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
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
            "conversions": round(float(r.conversions or 0), 1),
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


# ── Health Check — powers dashboard widgets ──────────────────────────────────

@router.get("/health-check")
async def get_health_check(
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Lightweight account health check. Returns:
    - wasted spend breakdown (keywords, search terms, low-CTR ads)
    - top money-making keywords
    - account status summary
    - optimizer status
    - problem count for "Fix My Ads" button
    """
    start_date = date.today() - timedelta(days=days)
    tid = user.tenant_id

    # ── 1. Wasted keywords: cost > $10, 0 conversions, 10+ clicks ────────
    kw_sub = (
        select(
            KeywordPerformanceDaily.keyword_id,
            func.sum(KeywordPerformanceDaily.cost_micros).label("total_cost"),
            func.sum(KeywordPerformanceDaily.clicks).label("total_clicks"),
            func.sum(KeywordPerformanceDaily.conversions).label("total_conv"),
        )
        .where(
            KeywordPerformanceDaily.tenant_id == tid,
            KeywordPerformanceDaily.date >= start_date,
        )
        .group_by(KeywordPerformanceDaily.keyword_id)
        .subquery()
    )
    wasted_kw = await db.execute(
        select(
            func.sum(kw_sub.c.total_cost).label("cost"),
            func.count().label("count"),
        ).where(
            kw_sub.c.total_conv == 0,
            kw_sub.c.total_clicks >= 10,
            kw_sub.c.total_cost >= 10_000_000,  # $10 in micros
        )
    )
    wk = wasted_kw.one_or_none()
    wasted_keyword_cost = round(float(wk.cost or 0) / 1_000_000, 2) if wk else 0
    wasted_keyword_count = int(wk.count or 0) if wk else 0

    # ── 2. Wasted search terms: cost > $5, 0 conversions ─────────────────
    st_sub = (
        select(
            SearchTermPerformance.search_term,
            func.sum(SearchTermPerformance.cost_micros).label("total_cost"),
            func.sum(SearchTermPerformance.conversions).label("total_conv"),
        )
        .where(
            SearchTermPerformance.tenant_id == tid,
            SearchTermPerformance.date >= start_date,
        )
        .group_by(SearchTermPerformance.search_term)
        .subquery()
    )
    wasted_st = await db.execute(
        select(
            func.sum(st_sub.c.total_cost).label("cost"),
            func.count().label("count"),
        ).where(
            st_sub.c.total_conv == 0,
            st_sub.c.total_cost >= 5_000_000,  # $5 in micros
        )
    )
    ws = wasted_st.one_or_none()
    wasted_search_term_cost = round(float(ws.cost or 0) / 1_000_000, 2) if ws else 0
    wasted_search_term_count = int(ws.count or 0) if ws else 0

    # ── 3. Low-CTR ads: CTR < 2%, 100+ impressions ───────────────────────
    ad_sub = (
        select(
            AdPerformanceDaily.ad_id,
            func.sum(AdPerformanceDaily.cost_micros).label("total_cost"),
            func.sum(AdPerformanceDaily.impressions).label("total_imp"),
            func.sum(AdPerformanceDaily.clicks).label("total_clicks"),
        )
        .where(
            AdPerformanceDaily.tenant_id == tid,
            AdPerformanceDaily.date >= start_date,
        )
        .group_by(AdPerformanceDaily.ad_id)
        .subquery()
    )
    wasted_ads = await db.execute(
        select(
            func.sum(ad_sub.c.total_cost).label("cost"),
            func.count().label("count"),
        ).where(
            ad_sub.c.total_imp >= 100,
            (ad_sub.c.total_clicks * 1.0 / ad_sub.c.total_imp) < 0.02,
        )
    )
    wa = wasted_ads.one_or_none()
    wasted_ad_cost = round(float(wa.cost or 0) / 1_000_000, 2) if wa else 0
    wasted_ad_count = int(wa.count or 0) if wa else 0

    # ── 4. Top money keywords (by conversion_value) ──────────────────────
    money_kw = await db.execute(
        select(
            KeywordPerformanceDaily.keyword_text,
            KeywordPerformanceDaily.keyword_id,
            func.sum(KeywordPerformanceDaily.cost_micros).label("cost"),
            func.sum(KeywordPerformanceDaily.conversion_value).label("revenue"),
            func.sum(KeywordPerformanceDaily.conversions).label("conversions"),
            func.sum(KeywordPerformanceDaily.clicks).label("clicks"),
        )
        .where(
            KeywordPerformanceDaily.tenant_id == tid,
            KeywordPerformanceDaily.date >= start_date,
        )
        .group_by(KeywordPerformanceDaily.keyword_text, KeywordPerformanceDaily.keyword_id)
        .having(func.sum(KeywordPerformanceDaily.conversion_value) > 0)
        .order_by(desc("revenue"))
        .limit(10)
    )
    money_keywords = [
        {
            "keyword": r.keyword_text,
            "keyword_id": r.keyword_id,
            "spend": round(float(r.cost) / 1_000_000, 2),
            "revenue": round(float(r.revenue), 2),
            "conversions": round(float(r.conversions), 1),
            "clicks": int(r.clicks),
            "roas": round(float(r.revenue) / (float(r.cost) / 1_000_000), 2) if r.cost > 0 else 0,
        }
        for r in money_kw.all()
    ]

    # ── 5. Campaign status ───────────────────────────────────────────────
    camp_status = await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((Campaign.status == "ENABLED", 1), else_=0)).label("enabled"),
        ).where(Campaign.tenant_id == tid)
    )
    cs = camp_status.one_or_none()

    # ── 6. Optimizer status ──────────────────────────────────────────────
    tenant = await db.get(Tenant, str(tid))
    autonomy_mode = tenant.autonomy_mode if tenant else "suggest"

    from app.models.v2.optimization_cycle import OptimizationCycle
    last_cycle = await db.execute(
        select(OptimizationCycle)
        .where(OptimizationCycle.tenant_id == tid)
        .order_by(desc(OptimizationCycle.started_at))
        .limit(1)
    )
    lc = last_cycle.scalar_one_or_none()

    # ── 7. Budget-limited campaigns ──────────────────────────────────────
    # Check from PerformanceDaily if any campaign has high lost IS budget
    # (simplified: campaigns with status ENABLED but very low impression share)
    budget_limited_count = 0  # Will be populated from last scan if available
    from app.models.v2.operator_scan import OperatorScan
    from app.models.v2.operator_recommendation import OperatorRecommendation
    last_scan = await db.execute(
        select(OperatorScan)
        .where(OperatorScan.tenant_id == tid, OperatorScan.status == "ready")
        .order_by(desc(OperatorScan.created_at))
        .limit(1)
    )
    ls = last_scan.scalar_one_or_none()
    last_scan_problems = 0
    last_scan_id = None
    if ls:
        last_scan_id = ls.id
        rec_count = await db.execute(
            select(func.count()).where(OperatorRecommendation.scan_id == ls.id)
        )
        last_scan_problems = rec_count.scalar() or 0
        # Count budget-limited recs
        bl = await db.execute(
            select(func.count()).where(
                OperatorRecommendation.scan_id == ls.id,
                OperatorRecommendation.recommendation_type.in_(["INCREASE_BUDGET"]),
            )
        )
        budget_limited_count = bl.scalar() or 0

    # ── Problem count (for Fix My Ads button) ────────────────────────────
    problem_count = wasted_keyword_count + wasted_search_term_count + wasted_ad_count + budget_limited_count
    total_wasted = round(wasted_keyword_cost + wasted_search_term_cost + wasted_ad_cost, 2)

    return {
        "period_days": days,
        "problems_found": problem_count,
        "total_wasted_spend": total_wasted,
        "wasted_spend": {
            "keywords": {"cost": wasted_keyword_cost, "count": wasted_keyword_count},
            "search_terms": {"cost": wasted_search_term_cost, "count": wasted_search_term_count},
            "low_ctr_ads": {"cost": wasted_ad_cost, "count": wasted_ad_count},
            "budget_limited": {"count": budget_limited_count},
        },
        "money_keywords": money_keywords,
        "account_status": {
            "campaigns_total": cs.total if cs else 0,
            "campaigns_enabled": cs.enabled if cs else 0,
            "autonomy_mode": autonomy_mode,
            "last_optimization": lc.created_at.isoformat() if lc else None,
            "last_optimization_status": lc.status if lc else None,
            "last_scan_id": last_scan_id,
            "last_scan_problems": last_scan_problems,
        },
    }


@router.get("/campaigns")
async def get_dashboard_campaigns(
    days: int = 30,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start_date = date.today() - timedelta(days=days) if days > 0 else None
    result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).limit(20)
    )
    campaigns = result.scalars().all()

    campaign_data = []
    for c in campaigns:
        filters = [
            PerformanceDaily.tenant_id == user.tenant_id,
            PerformanceDaily.entity_type == "campaign",
            PerformanceDaily.entity_id == (c.campaign_id or c.id),
        ]
        if start_date:
            filters.append(PerformanceDaily.date >= start_date)
        perf = await db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
            ).where(and_(*filters))
        )
        row = perf.one_or_none()
        impressions = int(row.impressions or 0) if row else 0
        clicks = int(row.clicks or 0) if row else 0
        cost_micros = float(row.cost_micros or 0) if row else 0.0
        conversions = float(row.conversions or 0) if row else 0.0

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
