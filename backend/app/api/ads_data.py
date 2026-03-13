"""
Ads Data API — Search terms, keyword/ad/ad-group performance, landing pages,
Google recommendations, keyword research, and all mutation endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, timedelta

from app.core.database import get_db
from app.core.deps import require_tenant, require_analyst, CurrentUser
from app.models.integration_google_ads import IntegrationGoogleAds
from app.models.search_term_performance import SearchTermPerformance
from app.models.keyword_performance_daily import KeywordPerformanceDaily
from app.models.ad_performance_daily import AdPerformanceDaily
from app.models.ad_group_performance_daily import AdGroupPerformanceDaily
from app.models.landing_page_performance import LandingPagePerformance
from app.models.google_recommendation import GoogleRecommendation
from app.models.change_log import ChangeLog
from app.models.conversion import Conversion

router = APIRouter()


def _get_date_range(days: int = 30):
    end = date.today()
    start = end - timedelta(days=days)
    return start, end


async def _get_client(db: AsyncSession, tenant_id: str):
    from app.integrations.google_ads.client import GoogleAdsClient
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == tenant_id,
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(404, "No active Google Ads integration")
    return GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token_encrypted=integration.refresh_token_encrypted,
        login_customer_id=integration.login_customer_id,
    ), integration


# ── SEARCH TERMS ─────────────────────────────────────────────────

@router.get("/search-terms")
async def get_search_terms(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = None,
    keyword: Optional[str] = None,
    min_cost_dollars: Optional[float] = None,
    zero_conversions: Optional[bool] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start, end = _get_date_range(days)
    query = select(
        SearchTermPerformance.search_term,
        SearchTermPerformance.campaign_id,
        SearchTermPerformance.ad_group_id,
        SearchTermPerformance.keyword_text,
        func.sum(SearchTermPerformance.impressions).label("impressions"),
        func.sum(SearchTermPerformance.clicks).label("clicks"),
        func.sum(SearchTermPerformance.cost_micros).label("cost_micros"),
        func.sum(SearchTermPerformance.conversions).label("conversions"),
        func.sum(SearchTermPerformance.conversion_value).label("conversion_value"),
    ).where(
        SearchTermPerformance.tenant_id == user.tenant_id,
        SearchTermPerformance.date >= start,
        SearchTermPerformance.date <= end,
    ).group_by(
        SearchTermPerformance.search_term,
        SearchTermPerformance.campaign_id,
        SearchTermPerformance.ad_group_id,
        SearchTermPerformance.keyword_text,
    )

    if campaign_id:
        query = query.having(SearchTermPerformance.campaign_id == campaign_id)
    if keyword:
        query = query.having(SearchTermPerformance.search_term.ilike(f"%{keyword}%"))
    if min_cost_dollars:
        query = query.having(func.sum(SearchTermPerformance.cost_micros) >= int(min_cost_dollars * 1_000_000))
    if zero_conversions:
        query = query.having(func.sum(SearchTermPerformance.conversions) == 0)

    query = query.order_by(desc("cost_micros")).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "search_term": r.search_term,
            "campaign_id": r.campaign_id,
            "ad_group_id": r.ad_group_id,
            "keyword_text": r.keyword_text,
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
            "cost_micros": int(r.cost_micros or 0),
            "conversions": round(float(r.conversions or 0), 2),
            "conversion_value": round(float(r.conversion_value or 0), 2),
            "ctr": round(int(r.clicks or 0) / max(int(r.impressions or 0), 1) * 100, 2),
            "cpc": round(float(r.cost_micros or 0) / max(int(r.clicks or 0), 1) / 1_000_000, 2),
            "cpa": round(float(r.cost_micros or 0) / max(float(r.conversions or 0), 0.01) / 1_000_000, 2) if (r.conversions or 0) > 0 else None,
        }
        for r in rows
    ]


@router.get("/search-terms/waste")
async def get_wasted_search_terms(
    days: int = Query(30, ge=7, le=90),
    min_cost_dollars: float = Query(5.0),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start, end = _get_date_range(days)
    query = select(
        SearchTermPerformance.search_term,
        SearchTermPerformance.campaign_id,
        func.sum(SearchTermPerformance.cost_micros).label("cost_micros"),
        func.sum(SearchTermPerformance.clicks).label("clicks"),
        func.sum(SearchTermPerformance.conversions).label("conversions"),
    ).where(
        SearchTermPerformance.tenant_id == user.tenant_id,
        SearchTermPerformance.date >= start,
        SearchTermPerformance.date <= end,
    ).group_by(
        SearchTermPerformance.search_term,
        SearchTermPerformance.campaign_id,
    ).having(
        and_(
            func.sum(SearchTermPerformance.conversions) == 0,
            func.sum(SearchTermPerformance.cost_micros) >= int(min_cost_dollars * 1_000_000),
        )
    ).order_by(desc("cost_micros")).limit(100)

    result = await db.execute(query)
    rows = result.all()
    total_waste = sum(float(r.cost_micros or 0) for r in rows)

    # ── Conversion tracking verification ──
    # Check if tenant has any conversion actions configured
    conv_actions_result = await db.execute(
        select(func.count()).select_from(Conversion).where(
            Conversion.tenant_id == user.tenant_id
        )
    )
    total_conv_actions = conv_actions_result.scalar() or 0

    active_conv_result = await db.execute(
        select(func.count()).select_from(Conversion).where(
            Conversion.tenant_id == user.tenant_id,
            Conversion.status == "ENABLED",
        )
    )
    active_conv_actions = active_conv_result.scalar() or 0

    # Check if ANY conversions were recorded across ALL search terms in the period
    any_conv_result = await db.execute(
        select(func.sum(SearchTermPerformance.conversions)).where(
            SearchTermPerformance.tenant_id == user.tenant_id,
            SearchTermPerformance.date >= start,
            SearchTermPerformance.date <= end,
        )
    )
    total_conversions_in_period = float(any_conv_result.scalar() or 0)

    # Determine tracking health
    if total_conv_actions == 0:
        tracking_status = "not_setup"
        tracking_message = "No conversion actions found in your Google Ads account. You need to set up conversion tracking before wasted spend data is meaningful."
    elif active_conv_actions == 0:
        tracking_status = "all_disabled"
        tracking_message = f"You have {total_conv_actions} conversion action(s) but none are enabled. Enable at least one conversion action so Google can track results."
    elif total_conversions_in_period == 0:
        tracking_status = "no_data"
        tracking_message = f"You have {active_conv_actions} active conversion action(s) but recorded 0 conversions in the last {days} days. Your tracking may not be firing correctly — verify your conversion tag is installed on your website or that call tracking is configured."
    else:
        tracking_status = "healthy"
        tracking_message = None

    return {
        "total_waste": round(total_waste / 1_000_000, 2),
        "count": len(rows),
        "conversion_tracking": {
            "status": tracking_status,
            "message": tracking_message,
            "total_actions": total_conv_actions,
            "active_actions": active_conv_actions,
            "conversions_in_period": round(total_conversions_in_period, 1),
        },
        "terms": [
            {
                "search_term": r.search_term,
                "campaign_id": r.campaign_id,
                "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
                "clicks": r.clicks,
            }
            for r in rows
        ],
    }


# ── KEYWORD PERFORMANCE ──────────────────────────────────────────

@router.get("/keywords/performance")
async def get_keyword_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = None,
    sort_by: str = Query("cost", regex="^(cost|clicks|conversions|conversion_value|ctr|quality_score)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start, end = _get_date_range(days)
    query = select(
        KeywordPerformanceDaily.keyword_id,
        KeywordPerformanceDaily.keyword_text,
        KeywordPerformanceDaily.match_type,
        KeywordPerformanceDaily.campaign_id,
        KeywordPerformanceDaily.ad_group_id,
        func.sum(KeywordPerformanceDaily.impressions).label("impressions"),
        func.sum(KeywordPerformanceDaily.clicks).label("clicks"),
        func.sum(KeywordPerformanceDaily.cost_micros).label("cost_micros"),
        func.sum(KeywordPerformanceDaily.conversions).label("conversions"),
        func.sum(KeywordPerformanceDaily.conversion_value).label("conversion_value"),
        func.max(KeywordPerformanceDaily.quality_score).label("quality_score"),
    ).where(
        KeywordPerformanceDaily.tenant_id == user.tenant_id,
        KeywordPerformanceDaily.date >= start,
        KeywordPerformanceDaily.date <= end,
    ).group_by(
        KeywordPerformanceDaily.keyword_id,
        KeywordPerformanceDaily.keyword_text,
        KeywordPerformanceDaily.match_type,
        KeywordPerformanceDaily.campaign_id,
        KeywordPerformanceDaily.ad_group_id,
    )

    if campaign_id:
        query = query.having(KeywordPerformanceDaily.campaign_id == campaign_id)

    sort_map = {
        "cost": desc("cost_micros"),
        "clicks": desc("clicks"),
        "conversions": desc("conversions"),
        "conversion_value": desc("conversion_value"),
        "ctr": desc("clicks"),
        "quality_score": desc("quality_score"),
    }
    query = query.order_by(sort_map.get(sort_by, desc("cost_micros")))
    query = query.offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "keyword_id": r.keyword_id,
            "keyword_text": r.keyword_text,
            "match_type": r.match_type,
            "campaign_id": r.campaign_id,
            "ad_group_id": r.ad_group_id,
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
            "conversions": round(float(r.conversions or 0), 2),
            "conversion_value": round(float(r.conversion_value or 0), 2),
            "ctr": round(int(r.clicks or 0) / max(int(r.impressions or 0), 1) * 100, 2),
            "cpc": round(float(r.cost_micros or 0) / max(int(r.clicks or 0), 1) / 1_000_000, 2),
            "quality_score": r.quality_score,
        }
        for r in rows
    ]


# ── AD PERFORMANCE ───────────────────────────────────────────────

@router.get("/ads/performance")
async def get_ad_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start, end = _get_date_range(days)
    query = select(
        AdPerformanceDaily.ad_id,
        AdPerformanceDaily.campaign_id,
        AdPerformanceDaily.ad_group_id,
        func.sum(AdPerformanceDaily.impressions).label("impressions"),
        func.sum(AdPerformanceDaily.clicks).label("clicks"),
        func.sum(AdPerformanceDaily.cost_micros).label("cost_micros"),
        func.sum(AdPerformanceDaily.conversions).label("conversions"),
        func.sum(AdPerformanceDaily.conversion_value).label("conversion_value"),
    ).where(
        AdPerformanceDaily.tenant_id == user.tenant_id,
        AdPerformanceDaily.date >= start,
        AdPerformanceDaily.date <= end,
    ).group_by(
        AdPerformanceDaily.ad_id,
        AdPerformanceDaily.campaign_id,
        AdPerformanceDaily.ad_group_id,
    )

    if campaign_id:
        query = query.having(AdPerformanceDaily.campaign_id == campaign_id)

    query = query.order_by(desc("cost_micros")).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    # Fetch ad details (headlines, descriptions) from the Ad table
    from app.models.ad import Ad
    ad_ids = [r.ad_id for r in rows]
    ad_details = {}
    if ad_ids:
        ad_result = await db.execute(
            select(Ad).where(Ad.tenant_id == user.tenant_id, Ad.ad_id.in_(ad_ids))
        )
        for ad in ad_result.scalars().all():
            ad_details[ad.ad_id] = {
                "headlines": ad.headlines_json,
                "descriptions": ad.descriptions_json,
                "final_urls": ad.final_urls_json,
                "status": ad.status,
            }

    return [
        {
            "ad_id": r.ad_id,
            "campaign_id": r.campaign_id,
            "ad_group_id": r.ad_group_id,
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
            "conversions": round(float(r.conversions or 0), 2),
            "conversion_value": round(float(r.conversion_value or 0), 2),
            "ctr": round(int(r.clicks or 0) / max(int(r.impressions or 0), 1) * 100, 2),
            "cpc": round(float(r.cost_micros or 0) / max(int(r.clicks or 0), 1) / 1_000_000, 2),
            **(ad_details.get(r.ad_id, {})),
        }
        for r in rows
    ]


# ── AD GROUP PERFORMANCE ─────────────────────────────────────────

@router.get("/ad-groups/performance")
async def get_ad_group_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start, end = _get_date_range(days)
    query = select(
        AdGroupPerformanceDaily.ad_group_id,
        AdGroupPerformanceDaily.campaign_id,
        func.sum(AdGroupPerformanceDaily.impressions).label("impressions"),
        func.sum(AdGroupPerformanceDaily.clicks).label("clicks"),
        func.sum(AdGroupPerformanceDaily.cost_micros).label("cost_micros"),
        func.sum(AdGroupPerformanceDaily.conversions).label("conversions"),
        func.sum(AdGroupPerformanceDaily.conversion_value).label("conversion_value"),
    ).where(
        AdGroupPerformanceDaily.tenant_id == user.tenant_id,
        AdGroupPerformanceDaily.date >= start,
        AdGroupPerformanceDaily.date <= end,
    ).group_by(
        AdGroupPerformanceDaily.ad_group_id,
        AdGroupPerformanceDaily.campaign_id,
    )

    if campaign_id:
        query = query.having(AdGroupPerformanceDaily.campaign_id == campaign_id)

    query = query.order_by(desc("cost_micros")).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    # Fetch ad group names
    from app.models.ad_group import AdGroup
    ag_ids_str = [r.ad_group_id for r in rows]
    ag_names = {}
    if ag_ids_str:
        ag_result = await db.execute(
            select(AdGroup).where(AdGroup.tenant_id == user.tenant_id)
        )
        for ag in ag_result.scalars().all():
            if ag.ad_group_id in ag_ids_str:
                ag_names[ag.ad_group_id] = ag.name

    return [
        {
            "ad_group_id": r.ad_group_id,
            "ad_group_name": ag_names.get(r.ad_group_id, ""),
            "campaign_id": r.campaign_id,
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
            "conversions": round(float(r.conversions or 0), 2),
            "conversion_value": round(float(r.conversion_value or 0), 2),
            "ctr": round(int(r.clicks or 0) / max(int(r.impressions or 0), 1) * 100, 2),
            "cpc": round(float(r.cost_micros or 0) / max(int(r.clicks or 0), 1) / 1_000_000, 2),
        }
        for r in rows
    ]


# ── LANDING PAGE PERFORMANCE ─────────────────────────────────────

@router.get("/landing-pages")
async def get_landing_pages(
    days: int = Query(30, ge=7, le=90),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    start, end = _get_date_range(days)
    query = select(
        LandingPagePerformance.landing_page_url,
        func.sum(LandingPagePerformance.impressions).label("impressions"),
        func.sum(LandingPagePerformance.clicks).label("clicks"),
        func.sum(LandingPagePerformance.cost_micros).label("cost_micros"),
        func.sum(LandingPagePerformance.conversions).label("conversions"),
        func.sum(LandingPagePerformance.conversion_value).label("conversion_value"),
        func.avg(LandingPagePerformance.mobile_friendly_click_rate).label("mobile_friendly_click_rate"),
        func.avg(LandingPagePerformance.speed_score).label("speed_score"),
    ).where(
        LandingPagePerformance.tenant_id == user.tenant_id,
        LandingPagePerformance.date >= start,
        LandingPagePerformance.date <= end,
    ).group_by(
        LandingPagePerformance.landing_page_url,
    ).order_by(desc("clicks")).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "landing_page_url": r.landing_page_url,
            "impressions": int(r.impressions or 0),
            "clicks": int(r.clicks or 0),
            "cost": round(float(r.cost_micros or 0) / 1_000_000, 2),
            "conversions": round(float(r.conversions or 0), 2),
            "conversion_value": round(float(r.conversion_value or 0), 2),
            "ctr": round(int(r.clicks or 0) / max(int(r.impressions or 0), 1) * 100, 2),
            "conversion_rate": round(float(r.conversions or 0) / max(int(r.clicks or 0), 1) * 100, 2),
            "mobile_friendly_click_rate": round(float(r.mobile_friendly_click_rate), 2) if r.mobile_friendly_click_rate else None,
            "speed_score": round(float(r.speed_score), 1) if r.speed_score else None,
        }
        for r in rows
    ]


# ── PAGESPEED INSIGHTS ──────────────────────────────────────────

import time as _time, logging as _logging
_psi_cache: dict = {}        # {cache_key: (timestamp, result)}
_PSI_CACHE_TTL = 3600        # 1 hour
_psi_logger = _logging.getLogger("pagespeed")


@router.get("/landing-pages/pagespeed")
async def get_pagespeed(
    url: str = Query(...),
    strategy: str = Query("mobile", regex="^(mobile|desktop)$"),
    user: CurrentUser = Depends(require_tenant),
):
    """Fetch Google PageSpeed Insights scores for a landing page URL."""
    import httpx
    from app.core.config import settings

    # Check in-memory cache first (avoids rate limits on rapid page loads)
    cache_key = f"{url}|{strategy}"
    cached = _psi_cache.get(cache_key)
    if cached and (_time.time() - cached[0]) < _PSI_CACHE_TTL:
        return cached[1]

    psi_url = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if settings.GOOGLE_API_KEY:
        params["key"] = settings.GOOGLE_API_KEY

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(psi_url, params=params)
            if resp.status_code != 200:
                body = resp.text[:500]
                _psi_logger.warning(
                    "PageSpeed API error: status=%s body=%s url=%s",
                    resp.status_code, body, url,
                )
                raise HTTPException(502, f"PageSpeed API returned {resp.status_code}")
            data = resp.json()

        lighthouse = data.get("lighthouseResult", {})
        categories = lighthouse.get("categories", {})
        audits = lighthouse.get("audits", {})

        perf_score = categories.get("performance", {}).get("score")
        perf_score = round(perf_score * 100) if perf_score is not None else None

        # Core Web Vitals
        fcp = audits.get("first-contentful-paint", {}).get("numericValue")
        lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
        cls_val = audits.get("cumulative-layout-shift", {}).get("numericValue")
        tbt = audits.get("total-blocking-time", {}).get("numericValue")
        si = audits.get("speed-index", {}).get("numericValue")

        # Mobile friendly check from the loading experience
        loading_exp = data.get("loadingExperience", {})
        overall_category = loading_exp.get("overall_category", "NONE")

        result = {
            "url": url,
            "strategy": strategy,
            "performance_score": perf_score,
            "fcp_ms": round(fcp) if fcp else None,
            "lcp_ms": round(lcp) if lcp else None,
            "cls": round(cls_val, 3) if cls_val is not None else None,
            "tbt_ms": round(tbt) if tbt else None,
            "speed_index_ms": round(si) if si else None,
            "overall_category": overall_category,
        }

        # Cache the successful result
        _psi_cache[cache_key] = (_time.time(), result)
        return result
    except httpx.TimeoutException:
        raise HTTPException(504, "PageSpeed Insights timed out — try again")
    except HTTPException:
        raise
    except Exception as e:
        _psi_logger.error("PageSpeed error: %s url=%s", str(e), url)
        raise HTTPException(502, f"PageSpeed error: {str(e)}")


# ── GOOGLE RECOMMENDATIONS ───────────────────────────────────────

@router.get("/google-recommendations")
async def get_google_recommendations(
    status: Optional[str] = None,
    rec_type: Optional[str] = None,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(GoogleRecommendation).where(
        GoogleRecommendation.tenant_id == user.tenant_id
    )
    if status:
        query = query.where(GoogleRecommendation.status == status)
    if rec_type:
        query = query.where(GoogleRecommendation.type == rec_type)
    query = query.order_by(desc(GoogleRecommendation.synced_at)).limit(200)

    result = await db.execute(query)
    recs = result.scalars().all()
    return [
        {
            "id": r.id,
            "resource_name": r.recommendation_resource_name,
            "type": r.type,
            "campaign_id": r.campaign_id,
            "campaign_name": r.campaign_name,
            "ad_group_id": r.ad_group_id,
            "impact_base": r.impact_base_metrics,
            "impact_potential": r.impact_potential_metrics,
            "details": r.details,
            "status": r.status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
        }
        for r in recs
    ]


@router.post("/recommendations/{rec_id}/apply")
async def apply_recommendation(
    rec_id: str,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GoogleRecommendation).where(
            GoogleRecommendation.id == rec_id,
            GoogleRecommendation.tenant_id == user.tenant_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    if rec.status != "pending":
        raise HTTPException(400, f"Recommendation already {rec.status}")

    client, integration = await _get_client(db, user.tenant_id)
    api_result = await client.apply_google_recommendation(rec.recommendation_resource_name)

    if api_result.get("status") == "applied":
        from datetime import datetime, timezone
        rec.status = "applied"
        rec.applied_at = datetime.now(timezone.utc)
        await db.flush()
        return {"status": "applied", "recommendation_id": rec_id}
    else:
        raise HTTPException(500, api_result.get("error", "Failed to apply"))


@router.post("/recommendations/{rec_id}/dismiss")
async def dismiss_recommendation(
    rec_id: str,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GoogleRecommendation).where(
            GoogleRecommendation.id == rec_id,
            GoogleRecommendation.tenant_id == user.tenant_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(404, "Recommendation not found")

    client, integration = await _get_client(db, user.tenant_id)
    api_result = await client.dismiss_google_recommendation(rec.recommendation_resource_name)

    if api_result.get("status") == "dismissed":
        from datetime import datetime, timezone
        rec.status = "dismissed"
        rec.dismissed_at = datetime.now(timezone.utc)
        await db.flush()
        return {"status": "dismissed", "recommendation_id": rec_id}
    else:
        raise HTTPException(500, api_result.get("error", "Failed to dismiss"))


# ── SYNC GOOGLE RECOMMENDATIONS MANUALLY ─────────────────────────

@router.post("/google-recommendations/sync")
async def sync_google_recommendations(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Manually fetch Google recommendations from the API and upsert into DB."""
    from datetime import datetime, timezone
    import structlog
    logger = structlog.get_logger()

    client, integration = await _get_client(db, user.tenant_id)

    try:
        g_recs = await client.get_google_recommendations()
    except Exception as e:
        logger.error("Google recommendations fetch failed", error=str(e))
        return {"status": "error", "error": str(e), "synced": 0}

    synced = 0
    for gr in g_recs:
        existing_gr = await db.execute(
            select(GoogleRecommendation).where(
                GoogleRecommendation.recommendation_resource_name == gr["resource_name"]
            )
        )
        grobj = existing_gr.scalar_one_or_none()
        if not grobj:
            grobj = GoogleRecommendation(
                tenant_id=user.tenant_id,
                google_customer_id=integration.customer_id,
                recommendation_resource_name=gr["resource_name"],
                type=gr["type"],
                campaign_id=gr.get("campaign_id"),
                campaign_name=gr.get("campaign_name", ""),
                ad_group_id=gr.get("ad_group_id"),
                impact_base_metrics=gr.get("impact_base", {}),
                impact_potential_metrics=gr.get("impact_potential", {}),
                details=gr.get("details", {}),
            )
            db.add(grobj)
        else:
            grobj.impact_base_metrics = gr.get("impact_base", {})
            grobj.impact_potential_metrics = gr.get("impact_potential", {})
            grobj.details = gr.get("details", {})
            grobj.synced_at = datetime.now(timezone.utc)
        synced += 1

    await db.flush()
    return {
        "status": "ok",
        "synced": synced,
        "total_from_google": len(g_recs),
        "types": list(set(gr["type"] for gr in g_recs)) if g_recs else [],
    }


# ── KEYWORD RESEARCH ─────────────────────────────────────────────

class KeywordIdeasRequest(BaseModel):
    seed_keywords: List[str]
    location_id: str = "2840"
    language_id: str = "1000"


@router.post("/keyword-ideas")
async def get_keyword_ideas(
    req: KeywordIdeasRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    ideas = await client.get_keyword_ideas(
        seed_keywords=req.seed_keywords,
        location_id=req.location_id,
        language_id=req.language_id,
    )
    return {
        "count": len(ideas),
        "ideas": [
            {
                "keyword": i["keyword"],
                "avg_monthly_searches": i["avg_monthly_searches"],
                "competition": i["competition"],
                "low_bid": round(i["low_top_of_page_bid_micros"] / 1_000_000, 2) if i["low_top_of_page_bid_micros"] else 0,
                "high_bid": round(i["high_top_of_page_bid_micros"] / 1_000_000, 2) if i["high_top_of_page_bid_micros"] else 0,
            }
            for i in ideas
        ],
    }


# ── MUTATIONS ────────────────────────────────────────────────────

class NegativeKeywordsRequest(BaseModel):
    campaign_id: str
    keywords: List[str]


@router.post("/negative-keywords")
async def add_negative_keywords(
    req: NegativeKeywordsRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.add_negative_keywords(req.campaign_id, req.keywords)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


class UpdateBidRequest(BaseModel):
    ad_group_id: str
    criterion_id: str
    new_cpc_bid_micros: int


@router.patch("/keywords/{keyword_id}/bid")
async def update_keyword_bid(
    keyword_id: str,
    req: UpdateBidRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.update_keyword_bid(req.ad_group_id, req.criterion_id, req.new_cpc_bid_micros)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


class UpdateStatusRequest(BaseModel):
    status: str  # ENABLED or PAUSED


@router.patch("/keywords/{keyword_id}/status")
async def update_keyword_status(
    keyword_id: str,
    req: UpdateStatusRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    # Find the keyword to get ad_group_id
    from app.models.keyword import Keyword
    kw_result = await db.execute(
        select(Keyword).where(Keyword.keyword_id == keyword_id, Keyword.tenant_id == user.tenant_id)
    )
    kw = kw_result.scalar_one_or_none()
    if not kw:
        raise HTTPException(404, "Keyword not found")

    # Get the Google ad_group_id
    from app.models.ad_group import AdGroup
    ag_result = await db.execute(select(AdGroup).where(AdGroup.id == kw.ad_group_id))
    ag = ag_result.scalar_one_or_none()
    if not ag:
        raise HTTPException(404, "Ad group not found")

    client, integration = await _get_client(db, user.tenant_id)
    result = await client.update_keyword_status(ag.ad_group_id, keyword_id, req.status)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))

    kw.status = req.status
    await db.flush()
    return result


@router.patch("/ads/{ad_id}/status")
async def update_ad_status(
    ad_id: str,
    req: UpdateStatusRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    from app.models.ad import Ad
    from app.models.ad_group import AdGroup
    ad_result = await db.execute(
        select(Ad).where(Ad.ad_id == ad_id, Ad.tenant_id == user.tenant_id)
    )
    ad = ad_result.scalar_one_or_none()
    if not ad:
        raise HTTPException(404, "Ad not found")

    ag_result = await db.execute(select(AdGroup).where(AdGroup.id == ad.ad_group_id))
    ag = ag_result.scalar_one_or_none()
    if not ag:
        raise HTTPException(404, "Ad group not found")

    client, integration = await _get_client(db, user.tenant_id)
    result = await client.update_ad_status(ag.ad_group_id, ad_id, req.status)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))

    ad.status = req.status
    await db.flush()
    return result


@router.patch("/ad-groups/{ad_group_id}/status")
async def update_ad_group_status(
    ad_group_id: str,
    req: UpdateStatusRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.update_ad_group_status(ad_group_id, req.status)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


class DeviceBidModRequest(BaseModel):
    campaign_id: str
    device: str  # MOBILE, TABLET, DESKTOP
    bid_modifier: float  # e.g. 1.2 for +20%, 0.5 for -50%


@router.post("/device-bid-modifier")
async def set_device_bid_modifier(
    req: DeviceBidModRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.set_device_bid_modifier(req.campaign_id, req.device, req.bid_modifier)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


class LocationTargetRequest(BaseModel):
    campaign_id: str
    location_id: str


@router.post("/location-targeting")
async def add_location_targeting(
    req: LocationTargetRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.add_location_targeting(req.campaign_id, req.location_id)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


class ProximityTargetRequest(BaseModel):
    campaign_id: str
    latitude: float
    longitude: float
    radius_miles: float


@router.post("/proximity-targeting")
async def add_proximity_targeting(
    req: ProximityTargetRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.add_proximity_targeting(
        req.campaign_id, req.latitude, req.longitude, req.radius_miles
    )
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


class AdScheduleRequest(BaseModel):
    campaign_id: str
    day_of_week: str
    start_hour: int
    end_hour: int
    bid_modifier: float = 1.0


@router.post("/ad-schedule")
async def set_ad_schedule(
    req: AdScheduleRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.set_ad_schedule(
        req.campaign_id, req.day_of_week, req.start_hour, req.end_hour, req.bid_modifier
    )
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result


# ── OFFLINE CONVERSIONS ──────────────────────────────────────────

class OfflineConversionRequest(BaseModel):
    conversion_action_id: str
    conversions: List[dict]  # [{gclid, conversion_time, conversion_value, currency}]


@router.post("/conversions/upload")
async def upload_offline_conversions(
    req: OfflineConversionRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    client, integration = await _get_client(db, user.tenant_id)
    result = await client.upload_offline_conversions(req.conversions, req.conversion_action_id)
    if result.get("status") == "error":
        raise HTTPException(500, result.get("error"))
    return result
