"""
Public landing page serving endpoints - NO authentication required.
Serves published landing pages and tracks visitor events (visits, clicks, form submissions).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.business_profile import BusinessProfile
from app.models.landing_page import LandingPage, LandingPageEvent, LandingPageVariant
from app.services.operator.landing_page_agent import LandingPageAgent

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="", tags=["Landing Pages (Public)"])


# ── Request schemas ───────────────────────────────────────────────

class EventRequest(BaseModel):
    event_type: str  # call_click, form_submit, cta_click, scroll_depth
    gclid: Optional[str] = None
    metadata: Optional[dict] = None


# ── Helpers ───────────────────────────────────────────────────────

async def _get_published_page(slug: str, db: AsyncSession) -> LandingPage:
    """Fetch a landing page by slug, raising 404 if not serveable."""
    result = await db.execute(
        select(LandingPage).where(LandingPage.slug == slug)
    )
    page = result.scalar_one_or_none()

    if not page:
        raise HTTPException(status_code=404, detail="Landing page not found")

    if page.status not in ("published", "preview"):
        raise HTTPException(status_code=404, detail="Landing page not found")

    return page


def _pick_variant(page: LandingPage) -> LandingPageVariant:
    """Pick the best variant to serve: winner > first active > variant A."""
    variants = page.variants or []
    if not variants:
        raise HTTPException(status_code=404, detail="No variants available")

    # Prefer the declared winner
    for v in variants:
        if v.is_winner:
            return v

    # Fall back to first active variant
    for v in variants:
        if v.is_active:
            return v

    # Last resort: first variant (variant A)
    return variants[0]


async def _build_business_context(tenant_id: str, db: AsyncSession) -> dict:
    """Build the business context dict needed by the HTML renderer."""
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        return {}

    return {
        "business_name": profile.description or "",
        "phone": profile.phone or "",
        "website_url": profile.website_url or "",
        "industry": profile.industry_classification or "",
        "primary_conversion_goal": profile.primary_conversion_goal or "",
        "services": profile.services_json or {},
        "locations": profile.locations_json or {},
        "usp": profile.usp_json or {},
        "brand_voice": profile.brand_voice_json or {},
        "offers": profile.offers_json or {},
    }


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/lp/{slug}", response_class=HTMLResponse)
async def serve_landing_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Serve a published landing page by slug. Tracks a visit event."""
    page = await _get_published_page(slug, db)
    variant = _pick_variant(page)

    # Extract tracking params from query string
    params = request.query_params
    gclid = params.get("gclid")
    utm_source = params.get("utm_source")
    utm_medium = params.get("utm_medium")
    utm_campaign = params.get("utm_campaign")

    # Track visit event
    try:
        event = LandingPageEvent(
            landing_page_id=page.id,
            variant_id=variant.id,
            event_type="visit",
            gclid=gclid,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            metadata_json={
                "user_agent": request.headers.get("user-agent", ""),
                "referer": request.headers.get("referer", ""),
                "ip": request.client.host if request.client else None,
            },
        )
        db.add(event)
        await db.commit()
    except Exception as e:
        logger.warning("Failed to track visit event", slug=slug, error=str(e))
        await db.rollback()

    # Build business context and render HTML
    business_context = await _build_business_context(page.tenant_id, db)
    strategy = page.strategy_json or {}

    agent = LandingPageAgent(db=db, tenant_id=page.tenant_id)
    html = agent._render_preview_html(
        content=variant.content_json or {},
        business_context=business_context,
        strategy=strategy,
        slug=page.slug,
    )

    return HTMLResponse(content=html, status_code=200)


@router.post("/lp/{slug}/event")
async def track_event(
    slug: str,
    body: EventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Track a landing page event (call_click, form_submit, cta_click, scroll_depth)."""
    allowed_events = {"call_click", "form_submit", "cta_click", "scroll_depth"}
    if body.event_type not in allowed_events:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type. Must be one of: {', '.join(sorted(allowed_events))}",
        )

    # Fetch the page to get its ID (and confirm it exists / is published)
    page = await _get_published_page(slug, db)
    variant = _pick_variant(page)

    try:
        event = LandingPageEvent(
            landing_page_id=page.id,
            variant_id=variant.id,
            event_type=body.event_type,
            gclid=body.gclid,
            metadata_json=body.metadata or {},
        )
        db.add(event)
        await db.commit()
    except Exception as e:
        logger.error("Failed to track event", slug=slug, event_type=body.event_type, error=str(e))
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to record event")

    return JSONResponse(content={"status": "ok"}, status_code=200)
