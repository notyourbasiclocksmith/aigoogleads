"""
Brain API — Google Business Profile endpoints for Jarvis S2S calls.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_brain_api_key, S2SContext
from app.services.gbp_service import GBPService

router = APIRouter(prefix="/gbp")


@router.get("/health")
async def gbp_health(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.health_check(ctx.tenant_id)


# ── Reviews ─────────────────────────────────────────────────

@router.get("/reviews")
async def get_reviews(
    page_size: int = Query(50, ge=1, le=100),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.get_reviews(ctx.tenant_id, page_size)


@router.post("/reviews/{review_id}/reply")
async def reply_to_review(
    review_id: str,
    reply_text: str = Query(...),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.reply_to_review(ctx.tenant_id, review_id, reply_text)


@router.post("/reviews/{review_id}/ai-reply")
async def ai_reply_to_review(
    review_id: str,
    reviewer_name: str = Query(...),
    star_rating: int = Query(..., ge=1, le=5),
    comment: str = Query(""),
    business_name: str = Query(""),
    tone: str = Query("professional"),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.ai_reply_to_review(
        ctx.tenant_id, review_id,
        reviewer_name=reviewer_name, star_rating=star_rating,
        comment=comment, business_name=business_name, tone=tone,
    )


@router.delete("/reviews/{review_id}/reply")
async def delete_review_reply(
    review_id: str,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.delete_review_reply(ctx.tenant_id, review_id)


# ── Posts ───────────────────────────────────────────────────

@router.get("/posts")
async def get_posts(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.get_posts(ctx.tenant_id)


@router.post("/posts")
async def create_post(
    summary: str = Query(...),
    topic_type: str = Query("STANDARD"),
    media_url: Optional[str] = Query(None),
    cta_type: Optional[str] = Query(None),
    cta_url: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.create_post(
        ctx.tenant_id, summary, topic_type,
        media_url=media_url, cta_type=cta_type, cta_url=cta_url,
    )


@router.post("/posts/ai-create")
async def ai_create_post(
    topic: str = Query(...),
    business_name: str = Query(""),
    business_type: str = Query(""),
    include_image: bool = Query(False),
    cta_type: Optional[str] = Query(None),
    cta_url: Optional[str] = Query(None),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.ai_create_post(
        ctx.tenant_id, topic,
        business_name=business_name, business_type=business_type,
        include_image=include_image, cta_type=cta_type, cta_url=cta_url,
    )


@router.delete("/posts/{post_name:path}")
async def delete_post(
    post_name: str,
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.delete_post(ctx.tenant_id, post_name)


# ── Business Info ──────────────────────────────────────────

@router.get("/business-info")
async def get_business_info(
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.get_business_info(ctx.tenant_id)


@router.get("/insights")
async def get_insights(
    date_from: str = Query(...),
    date_to: str = Query(...),
    ctx: S2SContext = Depends(require_brain_api_key),
    db: AsyncSession = Depends(get_db),
):
    svc = GBPService(db)
    return await svc.get_insights(ctx.tenant_id, date_from, date_to)
