"""
Analytics API — Device, Hour-of-Day, Geo, Call Tracking, Campaign Detail

Endpoints:
- /device          — Performance by device (mobile/desktop/tablet)
- /hourly          — Performance by hour of day (heatmap data)
- /day-of-week     — Performance by day of week
- /geo             — Performance by geographic location
- /campaign/{id}   — Comprehensive campaign tracking with trends
- /calls           — CallFlux call tracking data
- /calls/attribution — GCLID → call attribution data
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.ads_account import IntegrationGoogleAds
from app.models.tenant import Tenant
from app.integrations.google_ads.client import GoogleAdsClient
from app.integrations.callflux.client import callflux_client

import structlog

logger = structlog.get_logger()

router = APIRouter()


# ── HELPERS ──────────────────────────────────────────────────

async def _get_ads_client(
    user: CurrentUser, db: AsyncSession, campaign_id: str = ""
) -> GoogleAdsClient:
    """Get an authenticated Google Ads client for the current tenant."""
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Google Ads not connected")
    return GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token_encrypted=integration.refresh_token_encrypted,
        login_customer_id=integration.login_customer_id,
    )


def _date_range_str(days: int) -> str:
    """Convert days integer to Google Ads date range string."""
    mapping = {
        7: "LAST_7_DAYS",
        14: "LAST_14_DAYS",
        30: "LAST_30_DAYS",
        90: "LAST_90_DAYS",
    }
    # Find closest supported range
    if days <= 7:
        return "LAST_7_DAYS"
    elif days <= 14:
        return "LAST_14_DAYS"
    elif days <= 30:
        return "LAST_30_DAYS"
    else:
        return "LAST_90_DAYS"


# ── DEVICE PERFORMANCE ──────────────────────────────────────

@router.get("/device")
async def get_device_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Performance breakdown by device type (MOBILE, DESKTOP, TABLET)."""
    client = await _get_ads_client(user, db)
    try:
        raw = await client.get_device_performance(
            date_range=_date_range_str(days),
            campaign_id=campaign_id or "",
        )
        # Aggregate by device
        devices = {}
        for row in raw:
            device = row["device"]
            if device not in devices:
                devices[device] = {
                    "device": device,
                    "impressions": 0, "clicks": 0, "cost_micros": 0,
                    "conversions": 0.0, "conv_value": 0.0,
                }
            d = devices[device]
            d["impressions"] += row["impressions"]
            d["clicks"] += row["clicks"]
            d["cost_micros"] += row["cost_micros"]
            d["conversions"] += row["conversions"]
            d["conv_value"] += row["conv_value"]

        result = []
        for d in devices.values():
            cost = d["cost_micros"] / 1_000_000
            result.append({
                **d,
                "cost": cost,
                "ctr": d["clicks"] / d["impressions"] if d["impressions"] > 0 else 0,
                "cpc": cost / d["clicks"] if d["clicks"] > 0 else 0,
                "cpa": cost / d["conversions"] if d["conversions"] > 0 else 0,
                "roas": d["conv_value"] / cost if cost > 0 else 0,
            })
        return {"period_days": days, "devices": result}
    except Exception as e:
        logger.error("Device performance fetch failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── HOURLY PERFORMANCE (HEATMAP) ────────────────────────────

@router.get("/hourly")
async def get_hourly_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Performance by hour of day (0-23) — for heatmap visualization."""
    client = await _get_ads_client(user, db)
    try:
        raw = await client.get_hour_of_day_performance(
            date_range=_date_range_str(days),
            campaign_id=campaign_id or "",
        )
        # Aggregate by hour
        hours = {}
        for row in raw:
            h = row["hour"]
            if h not in hours:
                hours[h] = {
                    "hour": h,
                    "impressions": 0, "clicks": 0, "cost_micros": 0,
                    "conversions": 0.0, "conv_value": 0.0,
                }
            hr = hours[h]
            hr["impressions"] += row["impressions"]
            hr["clicks"] += row["clicks"]
            hr["cost_micros"] += row["cost_micros"]
            hr["conversions"] += row["conversions"]
            hr["conv_value"] += row["conv_value"]

        result = []
        for h in sorted(hours.values(), key=lambda x: x["hour"]):
            cost = h["cost_micros"] / 1_000_000
            result.append({
                **h,
                "cost": cost,
                "ctr": h["clicks"] / h["impressions"] if h["impressions"] > 0 else 0,
                "cpa": cost / h["conversions"] if h["conversions"] > 0 else 0,
            })

        # Fill missing hours with zeros
        hour_map = {h["hour"]: h for h in result}
        full_result = []
        for i in range(24):
            if i in hour_map:
                full_result.append(hour_map[i])
            else:
                full_result.append({
                    "hour": i, "impressions": 0, "clicks": 0,
                    "cost_micros": 0, "cost": 0, "conversions": 0,
                    "conv_value": 0, "ctr": 0, "cpa": 0,
                })

        return {"period_days": days, "hours": full_result}
    except Exception as e:
        logger.error("Hourly performance fetch failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── DAY OF WEEK PERFORMANCE ─────────────────────────────────

@router.get("/day-of-week")
async def get_day_of_week_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Performance by day of week."""
    client = await _get_ads_client(user, db)
    try:
        raw = await client.get_day_of_week_performance(
            date_range=_date_range_str(days),
            campaign_id=campaign_id or "",
        )
        days_map = {}
        for row in raw:
            dow = row["day_of_week"]
            if dow not in days_map:
                days_map[dow] = {
                    "day": dow, "impressions": 0, "clicks": 0,
                    "cost_micros": 0, "conversions": 0.0, "conv_value": 0.0,
                }
            d = days_map[dow]
            d["impressions"] += row["impressions"]
            d["clicks"] += row["clicks"]
            d["cost_micros"] += row["cost_micros"]
            d["conversions"] += row["conversions"]
            d["conv_value"] += row["conv_value"]

        # Order by day of week
        day_order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        result = []
        for day_name in day_order:
            d = days_map.get(day_name, {
                "day": day_name, "impressions": 0, "clicks": 0,
                "cost_micros": 0, "conversions": 0, "conv_value": 0,
            })
            cost = d["cost_micros"] / 1_000_000
            result.append({
                **d,
                "cost": cost,
                "ctr": d["clicks"] / d["impressions"] if d["impressions"] > 0 else 0,
                "cpa": cost / d["conversions"] if d["conversions"] > 0 else 0,
            })
        return {"period_days": days, "days": result}
    except Exception as e:
        logger.error("Day-of-week performance fetch failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── GEO PERFORMANCE ─────────────────────────────────────────

@router.get("/geo")
async def get_geo_performance(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Performance by geographic location (city/metro)."""
    client = await _get_ads_client(user, db)
    try:
        raw = await client.get_geo_performance(
            date_range=_date_range_str(days),
            campaign_id=campaign_id or "",
        )
        # Collect all criterion IDs for batch resolution
        all_criterion_ids = set()
        for row in raw:
            for key in ("city_criterion_id", "metro_criterion_id", "region_criterion_id"):
                if row.get(key) and row[key] != "0":
                    all_criterion_ids.add(row[key])

        # Batch resolve criterion IDs to human-readable names
        name_map = {}
        if all_criterion_ids:
            try:
                name_map = await client.resolve_geo_criterion_ids(list(all_criterion_ids))
            except Exception as resolve_err:
                logger.warning("Geo name resolution failed, using IDs", error=str(resolve_err))

        result = []
        for row in raw:
            cost = row["cost_micros"] / 1_000_000
            # Build location name from resolved criterion IDs
            location_name = (
                name_map.get(row.get("city_criterion_id", ""))
                or name_map.get(row.get("metro_criterion_id", ""))
                or name_map.get(row.get("region_criterion_id", ""))
                or row.get("city_criterion_id")
                or row.get("metro_criterion_id")
                or row.get("region_criterion_id")
                or "Unknown"
            )
            result.append({
                **row,
                "location_name": location_name,
                "cost": cost,
                "ctr": row["clicks"] / row["impressions"] if row["impressions"] > 0 else 0,
                "cpa": cost / row["conversions"] if row["conversions"] > 0 else 0,
            })
        return {"period_days": days, "locations": result}
    except Exception as e:
        logger.error("Geo performance fetch failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── CAMPAIGN DETAIL TRACKING ────────────────────────────────

@router.get("/campaign/{campaign_id}")
async def get_campaign_tracking(
    campaign_id: str,
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Comprehensive campaign tracking page data — KPIs, trends,
    device split, top keywords, top search terms, all in one call.
    """
    client = await _get_ads_client(user, db)
    date_range = _date_range_str(days)

    try:
        import asyncio

        # Fetch everything in parallel
        detail_task = client.get_campaign_performance_detail(campaign_id, date_range)
        device_task = client.get_device_performance(date_range, campaign_id)
        hourly_task = client.get_hour_of_day_performance(date_range, campaign_id)

        detail, device_raw, hourly_raw = await asyncio.gather(
            detail_task, device_task, hourly_task,
            return_exceptions=True,
        )

        # Handle errors gracefully
        if isinstance(detail, Exception):
            logger.warning("Campaign detail fetch failed", error=str(detail))
            detail = {"campaign_id": campaign_id, "trends": [], "totals": {}}
        if isinstance(device_raw, Exception):
            device_raw = []
        if isinstance(hourly_raw, Exception):
            hourly_raw = []

        # Process device data
        devices = {}
        for row in device_raw:
            device = row["device"]
            if device not in devices:
                devices[device] = {
                    "device": device, "impressions": 0, "clicks": 0,
                    "cost_micros": 0, "conversions": 0.0,
                }
            d = devices[device]
            d["impressions"] += row["impressions"]
            d["clicks"] += row["clicks"]
            d["cost_micros"] += row["cost_micros"]
            d["conversions"] += row["conversions"]
        device_result = []
        for d in devices.values():
            cost = d["cost_micros"] / 1_000_000
            device_result.append({
                **d, "cost": cost,
                "ctr": d["clicks"] / d["impressions"] if d["impressions"] > 0 else 0,
            })

        # Process hourly data
        hour_agg = {}
        for row in hourly_raw:
            h = row["hour"]
            if h not in hour_agg:
                hour_agg[h] = {"hour": h, "clicks": 0, "cost_micros": 0, "conversions": 0.0}
            hour_agg[h]["clicks"] += row["clicks"]
            hour_agg[h]["cost_micros"] += row["cost_micros"]
            hour_agg[h]["conversions"] += row["conversions"]
        hourly_result = []
        for i in range(24):
            h = hour_agg.get(i, {"hour": i, "clicks": 0, "cost_micros": 0, "conversions": 0})
            hourly_result.append({**h, "cost": h["cost_micros"] / 1_000_000})

        return {
            "campaign_id": campaign_id,
            "period_days": days,
            "totals": detail.get("totals", {}),
            "trends": detail.get("trends", []),
            "devices": device_result,
            "hourly": hourly_result,
        }
    except Exception as e:
        logger.error("Campaign tracking fetch failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ── CALL TRACKING (CALLFLUX) ────────────────────────────────

@router.get("/calls")
async def get_call_tracking(
    days: int = Query(30, ge=7, le=90),
    campaign_id: Optional[int] = Query(None, description="CallFlux campaign ID"),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch call tracking data from CallFlux — calls, durations,
    recordings, lead scores.
    """
    if not callflux_client.is_configured:
        return {"calls": [], "summary": {}, "status": "not_configured"}

    # Get tenant's CallFlux ID
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.callflux_tenant_id:
        return {"calls": [], "summary": {}, "status": "not_registered"}

    try:
        calls = await callflux_client.get_calls(
            callflux_tenant_id=tenant.callflux_tenant_id,
            campaign_id=campaign_id,
            days=days,
        )

        if not isinstance(calls, list):
            calls = []

        # Build summary
        total_calls = len(calls)
        answered = sum(1 for c in calls if c.get("status") == "answered")
        missed = sum(1 for c in calls if c.get("status") == "missed")
        total_duration = sum(c.get("duration_seconds", 0) for c in calls)
        avg_duration = total_duration / answered if answered > 0 else 0

        # Calls by hour for heatmap
        calls_by_hour = [0] * 24
        for c in calls:
            hour = c.get("hour", 0)
            if 0 <= hour < 24:
                calls_by_hour[hour] += 1

        # Calls by day for trend
        from collections import Counter
        calls_by_date = Counter(c.get("date", "unknown") for c in calls)

        summary = {
            "total_calls": total_calls,
            "answered": answered,
            "missed": missed,
            "answer_rate": answered / total_calls if total_calls > 0 else 0,
            "total_duration_seconds": total_duration,
            "avg_duration_seconds": round(avg_duration),
            "calls_by_hour": calls_by_hour,
            "calls_by_date": dict(calls_by_date),
        }

        return {
            "calls": calls[:200],  # Cap at 200 for response size
            "summary": summary,
            "status": "ok",
            "period_days": days,
        }
    except Exception as e:
        logger.error("CallFlux call fetch failed", error=str(e))
        return {"calls": [], "summary": {}, "status": "error", "error": str(e)}


@router.get("/calls/attribution")
async def get_call_attribution(
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    GCLID → call attribution data from CallFlux.
    Maps calls back to specific Google Ads clicks.
    """
    if not callflux_client.is_configured:
        return {"attribution": {}, "status": "not_configured"}

    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.callflux_tenant_id:
        return {"attribution": {}, "status": "not_registered"}

    try:
        attribution = await callflux_client.get_attribution(
            callflux_tenant_id=tenant.callflux_tenant_id,
            days=days,
        )
        return {
            "attribution": attribution,
            "status": "ok",
            "period_days": days,
        }
    except Exception as e:
        logger.error("CallFlux attribution fetch failed", error=str(e))
        return {"attribution": {}, "status": "error", "error": str(e)}
