"""
Campaign Strategist AI API — The AI Marketing Operator chat interface.
Handles the multi-step flow: intent → LP decision → campaign → audit → expand.
Also serves landing page CRUD, audit, and expansion endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.landing_page import LandingPage, LandingPageVariant, ExpansionRecommendation

import structlog

logger = structlog.get_logger()

router = APIRouter()


# ── STRATEGIST CHAT ───────────────────────────────────────────────

class StrategistMessage(BaseModel):
    message: str
    session_state: Dict[str, Any] = {}
    conversation_history: List[Dict[str, str]] = []
    action: Optional[str] = None  # quick action key


@router.post("/chat")
async def strategist_chat(
    req: StrategistMessage,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Main strategist chat endpoint. Processes user message through the
    orchestrator and returns AI reply + updated session state + quick actions.
    """
    from app.services.strategist_orchestrator import StrategistOrchestrator

    orchestrator = StrategistOrchestrator(db, str(user.tenant_id))

    # If an action button was clicked, translate to fallback message
    message = req.message
    if req.action and not message:
        action_messages = {
            "lp_existing": "I have an existing landing page",
            "lp_create": "Create a new AI landing page",
            "lp_skip": "Skip landing page for now",
            "generate_lp": "Generate a landing page for this campaign",
            "audit_campaign": "Audit this campaign for quality",
            "audit_all": "Audit everything",
            "expand_makes": "Show me expansion opportunities for similar makes",
            "expand_services": "Show me related service expansions",
            "expand": "Find expansion opportunities",
            "expand_5": "Generate the top 5 expansions",
            "expand_10": "Generate the top 10 expansions",
            "expand_25": "Generate the top 25 expansions",
            "expand_all": "Generate all expansions",
            "skip_expansion": "Skip expansions",
            "bulk_10": "Create 10 more campaigns",
            "bulk_25": "Create 25 more campaigns",
            "bulk_50": "Create 50 more campaigns",
            "bulk_custom": "Create campaigns for all expansions",
            "new_campaign": "I want to build a new campaign",
            "launch": "Approve and launch this campaign",
            "regenerate": "Fix the issues and regenerate",
            "adjust": "I want to adjust the campaign details",
            "mine_search_terms": "Run search term mining",
            "optimize": "Optimize my campaigns",
            "what_next": "What should I do next?",
        }
        message = action_messages.get(req.action, req.action)

    result = await orchestrator.process_message(
        user_message=message,
        conversation_history=req.conversation_history,
        session_state=req.session_state,
        action=req.action,
    )

    # If bulk generate was triggered, kick off the Celery task
    bulk = result.pop("bulk_generate", None)
    if bulk and bulk.get("service_variants"):
        from app.jobs.tasks import bulk_generate_campaigns_task
        intent = req.session_state.get("intent", {})
        base_prompt = intent.get("original_prompt", bulk.get("base_prompt", ""))
        task = bulk_generate_campaigns_task.delay(
            str(user.tenant_id),
            bulk["service_variants"],
            base_prompt,
        )
        result["bulk_task_id"] = task.id

    return result


# ── LANDING PAGE CRUD ─────────────────────────────────────────────

@router.get("/landing-pages")
async def list_landing_pages(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all landing pages for this tenant."""
    result = await db.execute(
        select(LandingPage)
        .where(LandingPage.tenant_id == user.tenant_id)
        .order_by(LandingPage.created_at.desc())
        .limit(100)
    )
    pages = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "service": p.service,
            "location": p.location,
            "status": p.status,
            "page_type": p.page_type,
            "is_ai_generated": p.is_ai_generated,
            "audit_score": p.audit_score,
            "variant_count": len(p.variants) if p.variants else 0,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "published_at": p.published_at.isoformat() if p.published_at else None,
        }
        for p in pages
    ]


@router.get("/landing-pages/{page_id}")
async def get_landing_page(
    page_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get full landing page with variants."""
    lp = await db.get(LandingPage, page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    return {
        "id": lp.id,
        "name": lp.name,
        "slug": lp.slug,
        "service": lp.service,
        "location": lp.location,
        "status": lp.status,
        "page_type": lp.page_type,
        "is_ai_generated": lp.is_ai_generated,
        "strategy": lp.strategy_json,
        "content": lp.content_json,
        "style": lp.style_json,
        "seo": lp.seo_json,
        "audit_score": lp.audit_score,
        "audit": lp.audit_json,
        "variants": [
            {
                "id": v.id,
                "key": v.variant_key,
                "name": v.variant_name,
                "content": v.content_json,
                "is_active": v.is_active,
                "is_winner": v.is_winner,
                "visits": v.visits,
                "conversions": v.conversions,
                "conversion_rate": v.conversion_rate,
            }
            for v in (lp.variants or [])
        ],
        "created_at": lp.created_at.isoformat() if lp.created_at else None,
    }


class UpdateLandingPageStatus(BaseModel):
    status: str  # draft, preview, published, paused, archived, suspended


@router.patch("/landing-pages/{page_id}/status")
async def update_landing_page_status(
    page_id: str,
    req: UpdateLandingPageStatus,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update landing page status."""
    from datetime import datetime, timezone

    lp = await db.get(LandingPage, page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    valid = {"draft", "preview", "published", "paused", "archived", "suspended"}
    if req.status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid}")

    lp.status = req.status
    if req.status == "published" and not lp.published_at:
        lp.published_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": page_id, "status": req.status}


# ── LANDING PAGE GENERATION ───────────────────────────────────────

class GenerateLandingPageRequest(BaseModel):
    service: str
    location: str = ""
    campaign_keywords: List[str] = []
    campaign_headlines: List[str] = []


@router.post("/landing-pages/generate")
async def generate_landing_page(
    req: GenerateLandingPageRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI landing page with 3 variants."""
    from app.services.landing_page_generator import LandingPageGenerator
    from app.models.business_profile import BusinessProfile

    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = bp_result.scalar_one_or_none()

    gen = LandingPageGenerator(db, str(user.tenant_id))
    result = await gen.generate(
        service=req.service,
        location=req.location,
        industry=profile.industry_classification if profile else "",
        business_name=profile.business_name if profile else "",
        phone=profile.phone if profile else "",
        website=profile.website_url if profile else "",
        usps=[u if isinstance(u, str) else u.get("text", "") for u in (profile.usp_json or [])] if profile else [],
        offers=[o if isinstance(o, str) else o.get("text", "") for o in (profile.offers_json or [])] if profile else [],
        campaign_keywords=req.campaign_keywords,
        campaign_headlines=req.campaign_headlines,
    )
    return result


# ── LANDING PAGE AUDIT ────────────────────────────────────────────

class AuditLandingPageRequest(BaseModel):
    url: Optional[str] = None
    landing_page_id: Optional[str] = None
    campaign_keywords: List[str] = []
    campaign_headlines: List[str] = []
    service: str = ""
    location: str = ""


@router.post("/landing-pages/audit")
async def audit_landing_page(
    req: AuditLandingPageRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Audit a landing page (by URL or generated page ID)."""
    from app.services.landing_page_auditor import LandingPageAuditor
    from datetime import datetime, timezone

    auditor = LandingPageAuditor(db, str(user.tenant_id))

    if req.url:
        result = await auditor.audit_url(
            url=req.url,
            campaign_keywords=req.campaign_keywords,
            campaign_headlines=req.campaign_headlines,
            service=req.service,
            location=req.location,
        )
    elif req.landing_page_id:
        lp = await db.get(LandingPage, req.landing_page_id)
        if not lp or str(lp.tenant_id) != str(user.tenant_id):
            raise HTTPException(404, "Landing page not found")

        result = await auditor.audit_generated(
            content_json=lp.content_json,
            campaign_keywords=req.campaign_keywords,
            campaign_headlines=req.campaign_headlines,
            service=lp.service or req.service,
            location=lp.location or req.location,
        )

        # Save audit to LP record
        lp.audit_score = result.get("overall_score", 0)
        lp.audit_json = result
        lp.last_audited_at = datetime.now(timezone.utc)
        await db.commit()
    else:
        raise HTTPException(400, "Provide either url or landing_page_id")

    return result


# ── CAMPAIGN AUDIT ────────────────────────────────────────────────

class AuditCampaignRequest(BaseModel):
    draft: Dict[str, Any]


@router.post("/campaign-audit")
async def audit_campaign(
    req: AuditCampaignRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Audit a campaign draft for quality issues."""
    from app.services.campaign_auditor import CampaignAuditor

    auditor = CampaignAuditor(db, str(user.tenant_id))
    result = await auditor.audit_draft(req.draft)
    return result


# ── EXPANSION SCORING ─────────────────────────────────────────────

class ScoreExpansionsRequest(BaseModel):
    source_campaign_name: str
    service: str
    location: str = ""
    industry: str = ""


@router.post("/expansion-score")
async def score_expansions(
    req: ScoreExpansionsRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Score expansion opportunities from a source campaign."""
    from app.services.expansion_scorer import ExpansionScorer

    scorer = ExpansionScorer(db, str(user.tenant_id))
    result = await scorer.score_expansions(
        source_campaign_name=req.source_campaign_name,
        service=req.service,
        location=req.location,
        industry=req.industry,
    )
    return result


@router.get("/expansions")
async def list_expansions(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all expansion recommendations for this tenant."""
    result = await db.execute(
        select(ExpansionRecommendation)
        .where(ExpansionRecommendation.tenant_id == user.tenant_id)
        .order_by(ExpansionRecommendation.score.desc())
        .limit(100)
    )
    recs = result.scalars().all()
    return [
        {
            "id": r.id,
            "expansion_type": r.expansion_type,
            "service_name": r.service_name,
            "score": r.score,
            "scoring": r.scoring_json,
            "campaign_prompt": r.campaign_prompt,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recs
    ]
