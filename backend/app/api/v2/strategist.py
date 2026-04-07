"""
Campaign Strategist AI API — The AI Marketing Operator chat interface.
Handles the multi-step flow: intent → LP decision → campaign → audit → expand.
Also serves landing page CRUD, audit, and expansion endpoints.
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
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


@router.post("/chat/stream")
async def strategist_chat_stream(
    req: StrategistMessage,
    request: Request,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming version of strategist chat.
    Streams real-time progress during campaign generation, then the final result.
    Events:
      {"type": "step", "step": "...", "status": "running|done", "detail": "..."}
      {"type": "text", "content": "..."}
      {"type": "complete", "data": {...full result...}}
      {"type": "error", "message": "..."}
    """
    from app.services.strategist_orchestrator import StrategistOrchestrator

    progress_queue: asyncio.Queue = asyncio.Queue()
    orchestrator = StrategistOrchestrator(db, str(user.tenant_id))
    orchestrator._progress_queue = progress_queue

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

    history = [{"role": "user", "content": message}]
    if req.conversation_history:
        history = req.conversation_history + [{"role": "user", "content": message}]

    async def event_stream():
        result_holder = {}
        error_holder = {}

        async def run_orchestrator():
            try:
                result = await orchestrator.process_message(
                    user_message=message,
                    conversation_history=history,
                    session_state=req.session_state,
                    action=req.action,
                )
                # Handle bulk generate
                bulk = result.pop("bulk_generate", None)
                if bulk and bulk.get("service_variants"):
                    from app.jobs.tasks import bulk_generate_campaigns_task
                    intent = req.session_state.get("intent", {})
                    base_prompt = intent.get("original_prompt", bulk.get("base_prompt", ""))
                    task_obj = bulk_generate_campaigns_task.delay(
                        str(user.tenant_id),
                        bulk["service_variants"],
                        base_prompt,
                    )
                    result["bulk_task_id"] = task_obj.id
                result_holder["data"] = result
            except Exception as e:
                logger.error("Streaming orchestrator error", error=str(e))
                error_holder["message"] = str(e)
            finally:
                await progress_queue.put({"type": "_done"})

        task = asyncio.create_task(run_orchestrator())

        try:
            # Stream progress events while orchestrator runs
            while True:
                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    if task.done():
                        break
                    continue

                if event.get("type") == "_done":
                    break

                yield f"data: {json.dumps(event)}\n\n"

            # Ensure the task is fully done before we release the DB session
            if not task.done():
                await task

            # Check for errors
            if error_holder:
                yield f"data: {json.dumps({'type': 'error', 'message': error_holder['message']})}\n\n"
                return

            # Stream the reply text in chunks for typewriter effect
            result = result_holder.get("data", {})
            reply = result.get("reply", "")
            if reply:
                # Stream in ~60-char chunks for smooth typewriter
                chunk_size = 60
                for i in range(0, len(reply), chunk_size):
                    chunk = reply[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"
                    await asyncio.sleep(0.03)  # 30ms between chunks

            # Send full result (without reply text, already streamed)
            yield f"data: {json.dumps({'type': 'complete', 'data': result})}\n\n"
        finally:
            # Always await task to prevent DB connection leak
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    image_engine: str = "google"  # google (default), dalle, flux, stability
    image_model: str = ""  # sub-model override (e.g. gemini-2.5-flash-image, flux-pro)


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

    # Get business name from Tenant (not on BusinessProfile)
    from app.models.tenant import Tenant
    tenant = await db.get(Tenant, str(user.tenant_id))
    biz_name = tenant.name if tenant else ""

    # Auto-enrich: pull keywords and headlines from active Google Ads campaigns
    auto_keywords = list(req.campaign_keywords) if req.campaign_keywords else []
    auto_headlines = list(req.campaign_headlines) if req.campaign_headlines else []
    trust_signals = []
    description = profile.description if profile and hasattr(profile, 'description') else ""

    if not auto_keywords or not auto_headlines:
        try:
            from app.models.integration_google_ads import IntegrationGoogleAds
            ads_result = await db.execute(
                select(IntegrationGoogleAds).where(
                    IntegrationGoogleAds.tenant_id == user.tenant_id,
                    IntegrationGoogleAds.is_active == True,
                )
            )
            integration = ads_result.scalar_one_or_none()
            if integration and integration.customer_id and integration.customer_id != "pending":
                from app.integrations.google_ads.client import GoogleAdsClient
                ads_client = GoogleAdsClient(
                    customer_id=integration.customer_id,
                    refresh_token_encrypted=integration.refresh_token_encrypted,
                    login_customer_id=integration.login_customer_id,
                )
                # Pull top converting keywords
                if not auto_keywords:
                    try:
                        kw_perf = await ads_client.get_keyword_performance("LAST_30_DAYS")
                        # Get keywords sorted by conversions then cost
                        sorted_kws = sorted(kw_perf, key=lambda k: (k.get("conversions", 0), k.get("cost", 0)), reverse=True)
                        auto_keywords = [k["text"] for k in sorted_kws[:15] if k.get("text")]
                    except Exception:
                        pass
                # Pull ad headlines for message-match
                if not auto_headlines:
                    try:
                        ad_perf = await ads_client.get_ad_performance("LAST_30_DAYS")
                        for ad in ad_perf[:5]:
                            auto_headlines.extend(ad.get("headlines", []))
                        auto_headlines = list(dict.fromkeys(auto_headlines))[:15]  # dedupe
                    except Exception:
                        pass
        except Exception:
            pass

    # Pull trust signals from GBP if available
    try:
        from app.models.v2.gbp_connection import GBPConnection
        gbp_result = await db.execute(
            select(GBPConnection).where(GBPConnection.tenant_id == user.tenant_id)
        )
        gbp = gbp_result.scalar_one_or_none()
        if gbp:
            if gbp.avg_rating:
                trust_signals.append(f"{gbp.avg_rating}★ Google Rating ({gbp.total_reviews or 0}+ reviews)")
            if gbp.business_name:
                trust_signals.append(f"Verified Google Business: {gbp.business_name}")
    except Exception:
        pass

    # Add profile trust signals
    if profile and hasattr(profile, 'trust_signals_json') and profile.trust_signals_json:
        ts = profile.trust_signals_json
        if isinstance(ts, list):
            trust_signals.extend(ts[:6])
        elif isinstance(ts, dict):
            trust_signals.extend([f"{k}: {v}" for k, v in ts.items() if v][:6])

    gen = LandingPageGenerator(db, str(user.tenant_id))
    result = await gen.generate(
        service=req.service,
        location=req.location,
        industry=profile.industry_classification if profile else "",
        business_name=biz_name,
        phone=profile.phone if profile else "",
        website=profile.website_url if profile else "",
        usps=[u if isinstance(u, str) else u.get("text", "") for u in (profile.usp_json or [])] if profile else [],
        offers=[o if isinstance(o, str) else o.get("text", "") for o in (profile.offers_json or [])] if profile else [],
        campaign_keywords=auto_keywords,
        campaign_headlines=auto_headlines,
        trust_signals=trust_signals,
        description=description,
        image_engine=req.image_engine,
        image_model=req.image_model,
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


# ── LANDING PAGE AI EDIT ──────────────────────────────────────────

class AiEditVariantRequest(BaseModel):
    variant_id: str
    prompt: str


@router.post("/landing-pages/{page_id}/ai-edit")
async def ai_edit_landing_page(
    page_id: str,
    req: AiEditVariantRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Apply an AI prompt-based edit to a landing page variant."""
    from app.services.landing_page_generator import LandingPageGenerator
    from app.models.business_profile import BusinessProfile
    from app.models.tenant import Tenant

    lp = await db.get(LandingPage, page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    variant = await db.get(LandingPageVariant, req.variant_id)
    if not variant or str(variant.landing_page_id) != page_id:
        raise HTTPException(404, "Variant not found")

    # Load business context so AI can reference real business details
    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    bp = bp_result.scalar_one_or_none()
    tenant = await db.get(Tenant, str(user.tenant_id))
    business_context = {
        "business_name": tenant.name if tenant else "",
        "phone": bp.phone if bp else "",
        "website": bp.website_url if bp else "",
        "city": bp.city if bp else "",
        "state": bp.state if bp else "",
        "google_rating": bp.google_rating if bp else None,
        "review_count": bp.review_count if bp else None,
        "industry": bp.industry_classification if bp else (tenant.industry if tenant else ""),
        "trust_signals": bp.trust_signals_json if bp else {},
        "services": bp.services_json if bp else {},
    }

    gen = LandingPageGenerator(db, str(user.tenant_id))
    result = await gen.ai_edit_variant(
        variant_content=variant.content_json or {},
        edit_prompt=req.prompt,
        strategy=lp.strategy_json,
        business_context=business_context,
    )

    if result.get("error"):
        raise HTTPException(500, result["error"])

    # Save updated content
    variant.content_json = result["content"]
    if lp.content_json and variant.variant_key == "A":
        lp.content_json = result["content"]
    await db.commit()

    return {
        "variant_id": variant.id,
        "variant_key": variant.variant_key,
        "content": variant.content_json,
        "edit_applied": result.get("edit_applied", ""),
    }


class GenerateHeroImageRequest(BaseModel):
    variant_id: str
    prompt: Optional[str] = None  # Custom prompt, or auto-generate from content
    engine: str = "google"  # google (default), dalle, flux, stability
    engine_model: str = ""  # sub-model override


@router.post("/landing-pages/{page_id}/generate-image")
async def generate_landing_page_image(
    page_id: str,
    req: GenerateHeroImageRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate or regenerate a hero image for a landing page variant using SEOpix."""
    from app.integrations.image_generator.client import ImageGeneratorClient
    from app.models.business_profile import BusinessProfile
    from app.models.tenant import Tenant

    lp = await db.get(LandingPage, page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    variant = await db.get(LandingPageVariant, req.variant_id)
    if not variant or str(variant.landing_page_id) != page_id:
        raise HTTPException(404, "Variant not found")

    img_client = ImageGeneratorClient()
    if not img_client.is_configured:
        raise HTTPException(503, "Image generator not configured")

    # Load business context
    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    bp = bp_result.scalar_one_or_none()
    tenant = await db.get(Tenant, str(user.tenant_id))

    content = variant.content_json or {}
    hero = content.get("hero", {})

    # Use custom prompt, or hero_image_prompt from content, or build default
    prompt = req.prompt or hero.get("hero_image_prompt", "")
    if not prompt:
        service = lp.service or "service"
        industry = bp.industry_classification if bp else (tenant.industry if tenant else "service")
        prompt = (
            f"Professional {industry} business photo: a licensed {service.lower()} expert "
            f"performing work for a customer. Clean uniform, professional tools, well-lit workspace. "
            f"Photorealistic, high quality, suitable for a landing page hero."
        )

    biz_name = tenant.name if tenant else "Business"
    metadata = {
        "businessName": biz_name,
        "businessType": bp.industry_classification if bp else "service",
        "city": bp.city if bp else "",
        "description": f"Professional {lp.service} by {biz_name}",
        "keywords": f"{lp.service}, {lp.location}, professional",
    }

    # Build engine-specific kwargs
    engine_kwargs = {}
    if req.engine_model:
        model_key = {"google": "google_model", "flux": "flux_model", "stability": "stability_model"}.get(req.engine)
        if model_key:
            engine_kwargs[model_key] = req.engine_model

    result = await img_client.generate_single(
        prompt=prompt,
        engine=req.engine,
        style="photorealistic",
        size="1792x1024",
        metadata=metadata,
        **engine_kwargs,
    )

    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Image generation failed"))

    # Store image URL in variant content
    hero["hero_image_url"] = result["image_url"]
    hero["hero_image_prompt"] = prompt
    content["hero"] = hero
    variant.content_json = content
    if lp.content_json and variant.variant_key == "A":
        lp.content_json = content
    await db.commit()

    return {
        "variant_id": variant.id,
        "image_url": result["image_url"],
        "prompt": prompt,
    }


class UpdateVariantContentRequest(BaseModel):
    content: Dict[str, Any]


@router.put("/landing-pages/{page_id}/variants/{variant_id}")
async def update_variant_content(
    page_id: str,
    variant_id: str,
    req: UpdateVariantContentRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Directly update a variant's content JSON."""
    lp = await db.get(LandingPage, page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    variant = await db.get(LandingPageVariant, variant_id)
    if not variant or str(variant.landing_page_id) != page_id:
        raise HTTPException(404, "Variant not found")

    variant.content_json = req.content
    await db.commit()
    return {"variant_id": variant.id, "content": variant.content_json}


class CloneLandingPageRequest(BaseModel):
    new_service: str = ""
    new_location: str = ""
    adapt_prompt: str = ""


@router.post("/landing-pages/{page_id}/clone")
async def clone_landing_page(
    page_id: str,
    req: CloneLandingPageRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Clone a landing page, optionally adapting for a new service/location."""
    from app.services.landing_page_generator import LandingPageGenerator

    lp = await db.get(LandingPage, page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    gen = LandingPageGenerator(db, str(user.tenant_id))
    result = await gen.clone_landing_page(
        source_lp=lp,
        new_service=req.new_service,
        new_location=req.new_location,
        adapt_prompt=req.adapt_prompt,
    )
    return result


class GenerateFromPromptRequest(BaseModel):
    prompt: str
    service: str = ""
    location: str = ""
    image_engine: str = "google"
    image_model: str = ""


@router.post("/landing-pages/generate-from-prompt")
async def generate_lp_from_prompt(
    req: GenerateFromPromptRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new AI landing page from a free-form prompt."""
    from app.services.landing_page_generator import LandingPageGenerator
    from app.models.business_profile import BusinessProfile
    from app.models.tenant import Tenant

    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = bp_result.scalar_one_or_none()
    tenant = await db.get(Tenant, str(user.tenant_id))
    biz_name = tenant.name if tenant else ""

    gen = LandingPageGenerator(db, str(user.tenant_id))
    result = await gen.generate(
        service=req.service or req.prompt[:100],
        location=req.location,
        industry=profile.industry_classification if profile else "",
        business_name=biz_name,
        phone=profile.phone if profile else "",
        website=profile.website_url if profile else "",
        usps=[u if isinstance(u, str) else u.get("text", "") for u in (profile.usp_json or [])] if profile else [],
        offers=[o if isinstance(o, str) else o.get("text", "") for o in (profile.offers_json or [])] if profile else [],
        image_engine=req.image_engine,
        image_model=req.image_model,
    )
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


# ── AUTO-BUILD ("Get Customers" flow) ────────────────────────────

class AutoBuildRequest(BaseModel):
    business_type: str  # e.g. "locksmith", "roofer"
    location: str  # e.g. "Dallas, TX"
    budget_monthly: int = 1500  # monthly budget in USD
    goal: str = "leads"  # leads, calls, brand_awareness
    urgency: str = "high"  # low, medium, high


@router.post("/auto-build")
async def auto_build_campaign(
    req: AutoBuildRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    "Get Customers" one-click campaign builder.
    Takes business type, location, budget, and goal — builds a full campaign.
    Returns the campaign draft with AI reasoning.
    """
    from app.models.business_profile import BusinessProfile
    from app.models.tenant import Tenant
    from app.services.campaign_generator import CampaignGeneratorService
    from app.models.campaign import Campaign

    # Load business profile
    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    bp = bp_result.scalar_one_or_none()
    if not bp:
        raise HTTPException(400, "Complete onboarding first — no business profile found")

    # Load tenant for google customer ID
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    # Get Google Ads customer ID
    from app.models.integration import IntegrationGoogleAds
    int_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = int_result.scalar_one_or_none()
    google_customer_id = integration.customer_id if integration else None

    # Build a rich prompt from the form data
    daily_budget = round(req.budget_monthly / 30)
    prompt = (
        f"Create a {req.urgency}-urgency Google Ads campaign for a {req.business_type} "
        f"business in {req.location}. "
        f"Monthly budget: ${req.budget_monthly} (${daily_budget}/day). "
        f"Primary goal: {req.goal}. "
        f"Focus on high-intent, ready-to-buy keywords. "
        f"Include call extensions and location targeting for {req.location}."
    )

    # Generate campaign
    generator = CampaignGeneratorService(db, str(user.tenant_id))
    try:
        draft = await generator.generate_from_prompt(
            prompt=prompt,
            business_profile=bp,
            google_customer_id=google_customer_id,
        )
    except Exception as e:
        logger.error("Auto-build campaign generation failed", error=str(e))
        raise HTTPException(500, f"Campaign generation failed: {str(e)}")

    # Save as draft Campaign record
    camp_data = draft.get("campaign", {})
    campaign = Campaign(
        tenant_id=user.tenant_id,
        google_customer_id=google_customer_id,
        type=camp_data.get("type", "SEARCH"),
        name=camp_data.get("name", f"{req.business_type.title()} — {req.location}"),
        status="DRAFT",
        objective=req.goal,
        budget_micros=daily_budget * 1_000_000,
        bidding_strategy=camp_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
        settings_json={
            "locations": camp_data.get("locations", []),
            "schedule": camp_data.get("schedule", {}),
            "device_bids": camp_data.get("device_bids", {}),
            "network": camp_data.get("settings", {}).get("network", "SEARCH"),
            "ad_groups": draft.get("ad_groups", []),
            "asset_groups": draft.get("asset_groups", []),
            "extensions": draft.get("extensions", {}),
            "keyword_strategy": draft.get("keyword_strategy", {}),
            "reasoning": draft.get("reasoning", {}),
            "builder_log": draft.get("builder_log", {}),
            "compliance": draft.get("compliance", {}),
            "source": "get_customers_auto_build",
        },
        is_draft=True,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return {
        "success": True,
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "campaign_type": camp_data.get("type", "SEARCH"),
        "budget_daily": daily_budget,
        "budget_monthly": req.budget_monthly,
        "ad_groups": len(draft.get("ad_groups", [])),
        "keywords": draft.get("keyword_strategy", {}).get("total_keywords", 0),
        "ads": sum(len(ag.get("ads", [])) for ag in draft.get("ad_groups", [])),
        "compliance": draft.get("compliance", {}),
        "reasoning": draft.get("reasoning", {}),
        "builder_log": draft.get("builder_log", {}),
        "draft": draft,
    }


@router.post("/auto-build/stream")
async def auto_build_stream(
    req: AutoBuildRequest,
    request: Request,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE streaming version of auto-build for live progress UI.
    """
    from app.models.business_profile import BusinessProfile
    from app.models.tenant import Tenant
    from app.services.campaign_generator import CampaignGeneratorService
    from app.models.campaign import Campaign

    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    bp = bp_result.scalar_one_or_none()
    if not bp:
        raise HTTPException(400, "Complete onboarding first")

    from app.models.integration import IntegrationGoogleAds
    int_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = int_result.scalar_one_or_none()
    google_customer_id = integration.customer_id if integration else None

    daily_budget = round(req.budget_monthly / 30)
    prompt = (
        f"Create a {req.urgency}-urgency Google Ads campaign for a {req.business_type} "
        f"business in {req.location}. Monthly budget: ${req.budget_monthly} (${daily_budget}/day). "
        f"Primary goal: {req.goal}. Focus on high-intent keywords. "
        f"Include call extensions and location targeting for {req.location}."
    )

    progress_queue: asyncio.Queue = asyncio.Queue()

    async def event_stream():
        result_holder = {}
        error_holder = {}

        async def run_build():
            try:
                generator = CampaignGeneratorService(db, str(user.tenant_id))
                draft = await generator.generate_from_prompt(
                    prompt=prompt,
                    business_profile=bp,
                    google_customer_id=google_customer_id,
                    progress_queue=progress_queue,
                )
                # Save campaign
                camp_data = draft.get("campaign", {})
                campaign = Campaign(
                    tenant_id=user.tenant_id,
                    google_customer_id=google_customer_id,
                    type=camp_data.get("type", "SEARCH"),
                    name=camp_data.get("name", f"{req.business_type.title()} — {req.location}"),
                    status="DRAFT",
                    objective=req.goal,
                    budget_micros=daily_budget * 1_000_000,
                    bidding_strategy=camp_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
                    settings_json={
                        "ad_groups": draft.get("ad_groups", []),
                        "asset_groups": draft.get("asset_groups", []),
                        "extensions": draft.get("extensions", {}),
                        "keyword_strategy": draft.get("keyword_strategy", {}),
                        "reasoning": draft.get("reasoning", {}),
                        "builder_log": draft.get("builder_log", {}),
                        "compliance": draft.get("compliance", {}),
                        "source": "get_customers_auto_build",
                    },
                    is_draft=True,
                )
                db.add(campaign)
                await db.commit()
                await db.refresh(campaign)

                result_holder["data"] = {
                    "success": True,
                    "campaign_id": campaign.id,
                    "campaign_name": campaign.name,
                    "campaign_type": camp_data.get("type", "SEARCH"),
                    "budget_daily": daily_budget,
                    "ad_groups": len(draft.get("ad_groups", [])),
                    "keywords": draft.get("keyword_strategy", {}).get("total_keywords", 0),
                    "ads": sum(len(ag.get("ads", [])) for ag in draft.get("ad_groups", [])),
                    "compliance": draft.get("compliance", {}),
                    "reasoning": draft.get("reasoning", {}),
                }
            except Exception as e:
                logger.error("Auto-build stream error", error=str(e))
                error_holder["message"] = str(e)
            finally:
                await progress_queue.put({"type": "_done"})

        task = asyncio.create_task(run_build())

        try:
            while True:
                try:
                    event = await asyncio.wait_for(progress_queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    if task.done():
                        break
                    continue

                if event.get("type") == "_done":
                    break

                yield f"data: {json.dumps(event)}\n\n"

            if not task.done():
                await task

            if error_holder:
                yield f"data: {json.dumps({'type': 'error', 'message': error_holder['message']})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'complete', 'data': result_holder.get('data', {})})}\n\n"
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
