"""
Growth Features API — Search Term Mining, Auto-Expand Services, Bulk Campaign Generation.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.integration_google_ads import IntegrationGoogleAds
from app.models.recommendation import Recommendation

import structlog

logger = structlog.get_logger()

router = APIRouter()


# ── SEARCH TERM MINING AI ─────────────────────────────────────────

class MineRequest(BaseModel):
    google_customer_id: str
    days: int = 30


@router.post("/search-term-mining/run")
async def run_search_term_mining(
    req: MineRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Run AI search term mining analysis (async via Celery or inline for small accounts)."""
    from app.services.search_term_miner import SearchTermMiner

    miner = SearchTermMiner(db, str(user.tenant_id))
    result = await miner.mine(req.google_customer_id, days=req.days)
    return result


@router.post("/search-term-mining/run-async")
async def run_search_term_mining_async(
    req: MineRequest,
    user: CurrentUser = Depends(require_tenant),
):
    """Kick off search term mining as a background Celery task."""
    from app.jobs.tasks import mine_search_terms_task

    task = mine_search_terms_task.delay(str(user.tenant_id), req.google_customer_id, req.days)
    return {"task_id": task.id, "status": "queued"}


@router.get("/search-term-mining/recommendations")
async def get_mining_recommendations(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get pending search term mining recommendations for this tenant."""
    result = await db.execute(
        select(Recommendation)
        .where(
            and_(
                Recommendation.tenant_id == user.tenant_id,
                Recommendation.category == "search_term_mining",
            )
        )
        .order_by(Recommendation.created_at.desc())
        .limit(100)
    )
    recs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "severity": r.severity,
            "rationale": r.rationale,
            "expected_impact": r.expected_impact,
            "risk_level": r.risk_level,
            "action_diff": r.action_diff,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recs
    ]


class ActionRecommendationRequest(BaseModel):
    action: str  # "apply" or "dismiss"


@router.post("/search-term-mining/recommendations/{rec_id}/action")
async def action_mining_recommendation(
    rec_id: str,
    req: ActionRecommendationRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Apply or dismiss a search term mining recommendation."""
    from datetime import datetime, timezone

    rec = await db.get(Recommendation, rec_id)
    if not rec or str(rec.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Recommendation not found")

    if req.action == "dismiss":
        rec.status = "dismissed"
        await db.commit()
        return {"status": "dismissed", "id": rec_id}

    if req.action == "apply":
        # TODO: Actually apply via Google Ads API (add keyword / add negative)
        rec.status = "applied"
        rec.applied_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "applied", "id": rec_id}

    raise HTTPException(400, f"Unknown action: {req.action}")


# ── AUTO-EXPAND SERVICES ──────────────────────────────────────────

@router.get("/service-expansion/suggestions")
async def get_expansion_suggestions(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """AI-powered analysis of services the business could expand into."""
    from app.services.service_expander import ServiceExpander

    expander = ServiceExpander(db, str(user.tenant_id))
    result = await expander.suggest_expansions()
    return result


class ExpandServiceRequest(BaseModel):
    campaign_prompt: str
    service_name: str


@router.post("/service-expansion/generate")
async def generate_expansion_campaign(
    req: ExpandServiceRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a campaign for an expanded service using the AI-generated prompt."""
    from app.services.campaign_generator import CampaignGeneratorService
    from app.models.business_profile import BusinessProfile

    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = bp_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(400, "Business profile required. Complete onboarding first.")

    generator = CampaignGeneratorService(db, str(user.tenant_id))
    draft = await generator.generate_from_prompt(req.campaign_prompt, profile)
    return {
        "service_name": req.service_name,
        "draft": draft,
    }


# ── BULK CAMPAIGN GENERATION ──────────────────────────────────────

class BulkGenerateRequest(BaseModel):
    base_prompt: str
    service_variants: List[str]


@router.post("/bulk-generate")
async def bulk_generate_campaigns(
    req: BulkGenerateRequest,
    user: CurrentUser = Depends(require_tenant),
):
    """
    Kick off bulk campaign generation as a background task.
    Each service variant gets its own campaign.
    """
    from app.jobs.tasks import bulk_generate_campaigns_task

    if not req.service_variants:
        raise HTTPException(400, "service_variants must not be empty")
    if len(req.service_variants) > 200:
        raise HTTPException(400, "Maximum 200 campaigns per batch")

    task = bulk_generate_campaigns_task.delay(
        str(user.tenant_id),
        req.service_variants,
        req.base_prompt,
    )
    return {
        "task_id": task.id,
        "status": "queued",
        "total": len(req.service_variants),
    }


@router.get("/bulk-generate/{task_id}/status")
async def bulk_generate_status(
    task_id: str,
    user: CurrentUser = Depends(require_tenant),
):
    """Check progress of a bulk campaign generation task."""
    from app.jobs.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)

    if result.state == "PROGRESS":
        meta = result.info or {}
        return {
            "status": "in_progress",
            "current": meta.get("current", 0),
            "total": meta.get("total", 0),
            "current_service": meta.get("current_service", ""),
            "completed": meta.get("completed", 0),
            "errors": meta.get("errors", 0),
            "progress_pct": round(meta.get("current", 0) / max(meta.get("total", 1), 1) * 100),
        }
    elif result.state == "SUCCESS":
        return {"status": "complete", "progress_pct": 100}
    elif result.state == "FAILURE":
        return {"status": "failed", "error": str(result.info)}
    elif result.state == "PENDING":
        return {"status": "queued", "progress_pct": 0}
    else:
        return {"status": result.state, "progress_pct": 0}
