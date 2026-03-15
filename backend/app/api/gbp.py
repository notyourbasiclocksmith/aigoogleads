"""
Google Business Profile API Router.
Handles: OAuth flow, location management, posts (CRUD + AI generate),
scheduling, reviews, and AI review responses.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.config import settings
from app.core.deps import require_tenant, CurrentUser

router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OAUTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/oauth/authorize")
async def gbp_authorize(
    user: CurrentUser = Depends(require_tenant),
    origin: str = Query("onboarding"),
):
    """Get GBP OAuth authorization URL."""
    from app.services.gbp_oauth_service import get_authorization_url
    url = get_authorization_url(user.tenant_id, origin=origin)
    return {"auth_url": url, "authorization_url": url}


@router.get("/oauth/callback")
async def gbp_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback from Google, store tokens."""
    from app.services.gbp_oauth_service import exchange_code_for_tokens

    parts = state.split(":")
    if len(parts) < 2 or parts[0] != "gbp":
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    tenant_id = parts[1]
    result = await exchange_code_for_tokens(code, tenant_id, db)
    await db.commit()

    # Redirect to frontend — settings or onboarding depending on origin
    frontend_url = settings.APP_URL
    origin = parts[2] if len(parts) > 2 else "onboarding"
    redirect_path = "/settings" if origin == "settings" else "/onboarding"
    return RedirectResponse(url=f"{frontend_url}{redirect_path}?gbp=connected", status_code=302)


@router.get("/oauth/status")
async def gbp_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Check if GBP is connected for this tenant."""
    from sqlalchemy import select
    from app.models.gbp_connection import GBPConnection

    result = await db.execute(
        select(GBPConnection).where(GBPConnection.tenant_id == user.tenant_id)
    )
    conn = result.scalar_one_or_none()
    return {
        "connected": bool(conn and conn.access_token_encrypted and conn.is_active),
        "location_name": conn.location_name if conn else None,
        "last_sync": conn.last_sync_at.isoformat() if conn and conn.last_sync_at else None,
    }


@router.delete("/oauth/disconnect")
async def gbp_disconnect(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect GBP by deactivating the connection."""
    from sqlalchemy import select
    from app.models.gbp_connection import GBPConnection

    result = await db.execute(
        select(GBPConnection).where(GBPConnection.tenant_id == user.tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="No GBP connection found")

    conn.is_active = False
    conn.access_token_encrypted = None
    conn.refresh_token_encrypted = None
    await db.commit()
    return {"status": "disconnected"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LOCATIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/accounts")
async def list_gbp_accounts(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List GBP accounts for the authenticated user."""
    from app.services.gbp_service import GBPService
    svc = GBPService(db)
    accounts = await svc.list_accounts(user.tenant_id)
    return {"accounts": accounts}


@router.get("/locations")
async def list_gbp_locations(
    account_name: str = Query(..., description="e.g. accounts/123456"),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List locations for a GBP account."""
    from app.services.gbp_service import GBPService
    svc = GBPService(db)
    locations = await svc.list_locations(user.tenant_id, account_name)
    return {"locations": locations}


class SelectLocationRequest(BaseModel):
    account_name: str
    location_name: str  # e.g. "locations/12345"


@router.post("/locations/select")
async def select_gbp_location(
    req: SelectLocationRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Select a GBP location during onboarding.
    Fetches full details + reviews, syncs to DB, and auto-populates BusinessProfile.
    """
    from app.services.gbp_service import GBPService
    from app.models.gbp_connection import GBPConnection
    from sqlalchemy import select

    svc = GBPService(db)

    # Fetch location details
    location_data = await svc.fetch_location_detail(user.tenant_id, req.location_name)
    if not location_data:
        raise HTTPException(status_code=400, detail="Could not fetch location from GBP")

    # Sync location to DB
    loc = await svc.sync_location_to_db(user.tenant_id, location_data, req.account_name)

    # Fetch reviews
    full_name = f"{req.account_name}/{req.location_name}"
    reviews_data = await svc.fetch_reviews(user.tenant_id, full_name)

    # Sync reviews
    review_count = await svc.sync_reviews_to_db(user.tenant_id, loc.id, reviews_data)

    # Update location metrics
    loc.google_rating = reviews_data.get("averageRating")
    loc.review_count = reviews_data.get("totalReviewCount", 0)

    # Auto-populate BusinessProfile
    await svc.populate_business_profile(user.tenant_id, location_data, reviews_data)

    # Update GBP connection with selected location
    conn_result = await db.execute(
        select(GBPConnection).where(GBPConnection.tenant_id == user.tenant_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn:
        conn.account_id = req.account_name
        conn.location_id = req.location_name
        conn.location_name = loc.business_name
        from datetime import datetime, timezone
        conn.last_sync_at = datetime.now(timezone.utc)

    await db.commit()

    return {
        "success": True,
        "location": {
            "id": loc.id,
            "business_name": loc.business_name,
            "city": loc.city,
            "state": loc.state,
            "phone": loc.phone,
            "rating": loc.google_rating,
            "review_count": loc.review_count,
            "primary_category": loc.primary_category,
        },
        "reviews_synced": review_count,
        "business_profile_updated": True,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GBP POSTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CreatePostRequest(BaseModel):
    location_id: str
    content: str
    post_type: str = "UPDATE"
    media_url: Optional[str] = None
    call_to_action: str = "LEARN_MORE"
    cta_url: Optional[str] = None
    title: Optional[str] = None


@router.post("/posts")
async def create_post(
    req: CreatePostRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a draft GBP post."""
    from app.services.gbp_post_service import GBPPostService
    svc = GBPPostService(db)
    post = await svc.create_post(
        tenant_id=user.tenant_id,
        location_id=req.location_id,
        content=req.content,
        post_type=req.post_type,
        media_url=req.media_url,
        call_to_action=req.call_to_action,
        cta_url=req.cta_url,
        title=req.title,
    )
    await db.commit()
    return {
        "success": True,
        "post_id": post.id,
        "status": post.status.value,
    }


@router.get("/posts")
async def list_posts(
    location_id: Optional[str] = None,
    limit: int = Query(50, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List GBP posts for tenant."""
    from app.services.gbp_post_service import GBPPostService
    svc = GBPPostService(db)
    posts = await svc.list_posts(user.tenant_id, location_id, limit)
    return {
        "posts": [
            {
                "id": p.id,
                "location_id": p.location_id,
                "post_type": p.post_type.value if hasattr(p.post_type, 'value') else p.post_type,
                "summary": p.summary[:150] + "..." if len(p.summary) > 150 else p.summary,
                "status": p.status.value if hasattr(p.status, 'value') else p.status,
                "auto_generated": p.auto_generated,
                "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "views": p.views_count,
                "clicks": p.clicks_count,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in posts
        ]
    }


@router.post("/posts/{post_id}/publish")
async def publish_post(
    post_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Publish a GBP post via the API."""
    from app.services.gbp_post_service import GBPPostService
    svc = GBPPostService(db)
    result = await svc.publish_post(user.tenant_id, post_id)
    await db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class SchedulePostRequest(BaseModel):
    scheduled_time: datetime


@router.post("/posts/{post_id}/schedule")
async def schedule_post(
    post_id: str,
    req: SchedulePostRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Schedule a GBP post for future publishing."""
    from app.services.gbp_post_service import GBPPostService
    svc = GBPPostService(db)
    result = await svc.schedule_post(user.tenant_id, post_id, req.scheduled_time)
    await db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a draft GBP post."""
    from app.services.gbp_post_service import GBPPostService
    svc = GBPPostService(db)
    deleted = await svc.delete_post(user.tenant_id, post_id)
    await db.commit()
    if not deleted:
        raise HTTPException(status_code=400, detail="Post not found or already published")
    return {"success": True}


class AutoGenerateRequest(BaseModel):
    location_id: str
    service: str
    keywords: List[str] = []
    headlines: List[str] = []
    offers: List[str] = []


@router.post("/posts/auto-generate")
async def auto_generate_posts(
    req: AutoGenerateRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """AI-generate GBP posts from campaign data."""
    from app.services.gbp_post_service import GBPPostService
    from app.models.business_profile import BusinessProfile
    from sqlalchemy import select

    # Get business context
    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    bp = bp_result.scalar_one_or_none()

    from app.models.tenant import Tenant
    t_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = t_result.scalar_one_or_none()

    svc = GBPPostService(db)
    posts = await svc.auto_generate_from_campaign(
        tenant_id=user.tenant_id,
        location_id=req.location_id,
        service=req.service,
        keywords=req.keywords,
        headlines=req.headlines,
        offers=req.offers,
        business_name=tenant.name if tenant else "",
        phone=bp.phone if bp else "",
        city=bp.city if bp else "",
    )
    await db.commit()

    return {
        "success": True,
        "posts_created": len(posts),
        "posts": [
            {
                "id": p.id,
                "post_type": p.post_type.value if hasattr(p.post_type, 'value') else p.post_type,
                "summary": p.summary,
                "status": "draft",
            }
            for p in posts
        ],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REVIEWS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/reviews/sync")
async def sync_reviews(
    location_id: str = Query(...),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Sync reviews from GBP API into local DB."""
    from app.services.gbp_review_service import GBPReviewService
    svc = GBPReviewService(db)
    result = await svc.sync_reviews(user.tenant_id, location_id)
    await db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/reviews")
async def list_reviews(
    location_id: Optional[str] = None,
    unresponded_only: bool = False,
    limit: int = Query(50, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List reviews with summary stats."""
    from app.services.gbp_review_service import GBPReviewService
    svc = GBPReviewService(db)
    return await svc.list_reviews(user.tenant_id, location_id, unresponded_only, limit)


class GenerateResponseRequest(BaseModel):
    review_id: str
    tone: str = "professional"  # professional, friendly, casual


@router.post("/reviews/generate-response")
async def generate_review_response(
    req: GenerateResponseRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """AI-generate a review response."""
    from app.services.gbp_review_service import GBPReviewService
    svc = GBPReviewService(db)
    result = await svc.generate_ai_response(user.tenant_id, req.review_id, req.tone)
    await db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/reviews/{review_id}/approve-reply")
async def approve_review_reply(
    review_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve AI-generated reply and post it to GBP."""
    from app.services.gbp_review_service import GBPReviewService
    svc = GBPReviewService(db)
    result = await svc.approve_and_post_reply(user.tenant_id, review_id)
    await db.commit()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class BulkResponseRequest(BaseModel):
    review_ids: List[str]
    tone: str = "professional"


@router.post("/reviews/bulk-generate")
async def bulk_generate_responses(
    req: BulkResponseRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Bulk generate AI responses for multiple reviews."""
    from app.services.gbp_review_service import GBPReviewService
    svc = GBPReviewService(db)
    results = await svc.bulk_generate_responses(user.tenant_id, req.review_ids, req.tone)
    await db.commit()
    return {"results": results}
