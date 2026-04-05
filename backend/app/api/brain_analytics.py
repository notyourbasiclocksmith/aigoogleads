"""
Brain Analytics API — S2S endpoints for GA4 and Google Search Console data.

Consumed by Jarvis GA4Connector and GSCConnector.
"""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_brain_api_key, S2SContext
from app.services.ga4_service import GA4Service
from app.services.gsc_service import GSCService

router = APIRouter()


# ── GA4 Endpoints ───────────────────────────────────────────────

@router.get("/ga4/status")
async def ga4_status(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_status(ctx.tenant_id)


@router.get("/ga4/overview")
async def ga4_overview(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_overview(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/traffic-sources")
async def ga4_traffic_sources(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_traffic_sources(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/landing-pages")
async def ga4_landing_pages(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_landing_pages(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/devices")
async def ga4_devices(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_device_breakdown(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/geo")
async def ga4_geo(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_geo_performance(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/daily")
async def ga4_daily(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_daily_trend(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/conversions")
async def ga4_conversions(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_conversion_events(ctx.tenant_id, date_from, date_to)


@router.get("/ga4/pages")
async def ga4_pages(
    date_from: str = "30daysAgo", date_to: str = "today",
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GA4Service(db).get_page_performance(ctx.tenant_id, date_from, date_to)


# ── Google Search Console Endpoints ─────────────────────────────

@router.get("/gsc/status")
async def gsc_status(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_status(ctx.tenant_id)


@router.get("/gsc/overview")
async def gsc_overview(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_overview(ctx.tenant_id, date_from, date_to)


@router.get("/gsc/queries")
async def gsc_queries(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    limit: int = 100,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_top_queries(ctx.tenant_id, date_from, date_to, limit)


@router.get("/gsc/pages")
async def gsc_pages(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    limit: int = 100,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_top_pages(ctx.tenant_id, date_from, date_to, limit)


@router.get("/gsc/query-pages")
async def gsc_query_pages(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    limit: int = 200,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_query_page_matrix(ctx.tenant_id, date_from, date_to, limit)


@router.get("/gsc/countries")
async def gsc_countries(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_country_performance(ctx.tenant_id, date_from, date_to)


@router.get("/gsc/devices")
async def gsc_devices(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_device_performance(ctx.tenant_id, date_from, date_to)


@router.get("/gsc/daily")
async def gsc_daily(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_daily_trend(ctx.tenant_id, date_from, date_to)


@router.get("/gsc/search-appearance")
async def gsc_search_appearance(
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await GSCService(db).get_search_appearance(ctx.tenant_id, date_from, date_to)
