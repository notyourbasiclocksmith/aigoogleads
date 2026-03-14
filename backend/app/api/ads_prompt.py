import json as json_lib
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.deps import require_tenant, require_analyst, CurrentUser
from app.models.business_profile import BusinessProfile
from app.models.campaign import Campaign

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str
    google_customer_id: Optional[str] = None


class SaveDraftRequest(BaseModel):
    draft: Dict[str, Any]


class ApproveLaunchRequest(BaseModel):
    draft_campaign_id: Optional[str] = None
    draft: Optional[Dict[str, Any]] = None


class RefineRequest(BaseModel):
    prompt: str


@router.post("/refine")
async def refine_prompt(
    req: RefineRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """
    Takes a rough/short user prompt and uses OpenAI to expand it into a
    detailed campaign brief.  Returns the expanded prompt so the user can
    review, edit, and confirm before triggering full generation.
    """
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()

    # Pull existing campaigns for context
    camp_result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).limit(20)
    )
    existing = camp_result.scalars().all()
    existing_names = [c.name for c in existing]

    # Build business context block
    if profile:
        services = profile.services_json if isinstance(profile.services_json, list) else []
        svc_names = [s if isinstance(s, str) else s.get("name", "") for s in services]
        locations = profile.locations_json if isinstance(profile.locations_json, list) else []
        loc_names = [l if isinstance(l, str) else l.get("name", "") for l in locations]
        offers = profile.offers_json if isinstance(profile.offers_json, list) else []
        offer_texts = [o if isinstance(o, str) else o.get("text", "") for o in offers]
        usps = profile.usp_json if isinstance(profile.usp_json, list) else []
        usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in usps]
        industry = (profile.industry_classification or "general").lower()
        phone = profile.phone or ""
        website = profile.website_url or ""
        conversion_goal = profile.primary_conversion_goal or "calls"
        constraints = profile.constraints_json or {}
        monthly_budget = constraints.get("monthly_budget", 0)
    else:
        svc_names = []
        loc_names = []
        offer_texts = []
        usp_texts = []
        industry = "general"
        phone = ""
        website = ""
        conversion_goal = "calls"
        monthly_budget = 0

    import json as _json
    from openai import AsyncOpenAI
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        # No AI available — just return the prompt as-is
        return {
            "original_prompt": req.prompt,
            "refined_prompt": req.prompt,
            "suggestions": [],
            "ai_powered": False,
        }

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    system = """You are a Google Ads campaign strategist helping a business owner
refine their campaign request. Your job is to take a short or vague request and
expand it into a clear, detailed campaign brief that will produce the best
possible Google Ads campaign.

You have access to the business's profile data. Use it to fill in gaps the user
didn't mention. Ask yourself: What services? What locations? What budget? What
goal? What urgency level? What offers or USPs should be highlighted?

You respond ONLY with valid JSON."""

    user_msg = f"""The user typed this rough campaign request:

"{req.prompt}"

BUSINESS PROFILE:
- Industry: {industry}
- Services: {_json.dumps(svc_names[:15])}
- Locations: {_json.dumps(loc_names[:10])}
- Phone: {phone}
- Website: {website}
- Active offers: {_json.dumps(offer_texts[:5])}
- USPs: {_json.dumps(usp_texts[:5])}
- Conversion goal: {conversion_goal}
- Monthly budget: {"$" + str(monthly_budget) if monthly_budget else "Not set"}
- Existing campaigns: {_json.dumps(existing_names[:10])}

INSTRUCTIONS:
1. Expand the user's rough prompt into a detailed, well-structured campaign brief
   (2-4 sentences). Include specifics from their business profile they may have
   forgotten to mention.
2. If the user mentioned a niche service, keep it as the focus — don't generalize.
3. Suggest a budget if they didn't mention one (based on industry norms).
4. Suggest locations if not specified (from their profile).
5. Include relevant offers/USPs from their profile.
6. Flag if this might overlap with their existing campaigns.
7. Provide 2-3 short suggestions for things the user might want to add or change.

Return JSON:
{{
  "refined_prompt": "The expanded, detailed campaign brief ready to generate...",
  "detected_services": ["service1", "service2"],
  "detected_locations": ["city1", "city2"],
  "detected_goal": "calls" | "leads" | "awareness",
  "detected_urgency": "high" | "normal",
  "suggested_budget": "$X/day",
  "overlap_warning": "Warning if overlaps with existing campaign, or null",
  "suggestions": [
    "Consider adding...",
    "You might want to...",
    "Tip: ..."
  ]
}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.5,
            max_tokens=1000,
        )
        content = response.choices[0].message.content
        if not content:
            return {
                "original_prompt": req.prompt,
                "refined_prompt": req.prompt,
                "suggestions": [],
                "ai_powered": False,
            }

        data = _json.loads(content)
        return {
            "original_prompt": req.prompt,
            "refined_prompt": data.get("refined_prompt", req.prompt),
            "detected_services": data.get("detected_services", []),
            "detected_locations": data.get("detected_locations", []),
            "detected_goal": data.get("detected_goal"),
            "detected_urgency": data.get("detected_urgency"),
            "suggested_budget": data.get("suggested_budget"),
            "overlap_warning": data.get("overlap_warning"),
            "suggestions": data.get("suggestions", []),
            "ai_powered": True,
        }
    except Exception as e:
        import structlog
        structlog.get_logger().error("Prompt refinement failed", error=str(e))
        return {
            "original_prompt": req.prompt,
            "refined_prompt": req.prompt,
            "suggestions": [],
            "ai_powered": False,
        }


@router.post("/generate")
async def generate_campaign(
    req: PromptRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete business profile setup first")

    from app.services.campaign_generator import CampaignGeneratorService
    generator = CampaignGeneratorService(db, user.tenant_id)
    draft = await generator.generate_from_prompt(
        prompt=req.prompt,
        business_profile=profile,
        google_customer_id=req.google_customer_id,
    )

    return draft


@router.post("/generate-stream")
async def generate_campaign_stream(
    req: PromptRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """
    SSE endpoint that streams step-by-step progress events during campaign generation.
    Each event is a JSON object with: step, status, message, and optional detail.
    The final event has step="complete" with the full draft in detail.
    """
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete business profile setup first")

    from app.services.campaign_generator import CampaignGeneratorService
    generator = CampaignGeneratorService(db, user.tenant_id)

    async def event_stream():
        try:
            async for event in generator.generate_from_prompt_streaming(
                prompt=req.prompt,
                business_profile=profile,
                google_customer_id=req.google_customer_id,
            ):
                data = json_lib.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as e:
            error_event = json_lib.dumps({"step": "error", "status": "error", "message": str(e)})
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/context")
async def get_prompt_context(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return {"profile": None, "existing_campaigns": []}

    campaigns_result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).limit(20)
    )
    campaigns = campaigns_result.scalars().all()

    return {
        "profile": {
            "website": profile.website_url,
            "industry": profile.industry_classification,
            "services": profile.services_json,
            "locations": profile.locations_json,
            "phone": profile.phone,
            "conversion_goal": profile.primary_conversion_goal,
            "offers": profile.offers_json,
            "brand_voice": profile.brand_voice_json,
        },
        "existing_campaigns": [
            {"id": c.id, "name": c.name, "type": c.type, "status": c.status}
            for c in campaigns
        ],
    }


@router.post("/save-draft")
async def save_draft(
    req: SaveDraftRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    from app.models.integration_google_ads import IntegrationGoogleAds
    acct_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
            IntegrationGoogleAds.customer_id != "pending",
        ).limit(1)
    )
    account = acct_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=400, detail="No active Google Ads account")

    d = req.draft
    camp_data = d.get("campaign", {})
    campaign = Campaign(
        tenant_id=user.tenant_id,
        google_customer_id=account.customer_id,
        type=camp_data.get("type", "SEARCH"),
        name=camp_data.get("name", "AI Campaign"),
        status="DRAFT",
        objective=camp_data.get("objective", "leads"),
        budget_micros=camp_data.get("budget_micros", 30_000_000),
        bidding_strategy=camp_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
        settings_json={
            "locations": camp_data.get("locations", []),
            "schedule": camp_data.get("schedule", {}),
            "device_bids": camp_data.get("device_bids", {}),
            "network": camp_data.get("settings", {}).get("network", "SEARCH"),
            "ad_groups": d.get("ad_groups", []),
            "extensions": d.get("extensions", {}),
            "keyword_strategy": d.get("keyword_strategy", {}),
            "reasoning": d.get("reasoning", {}),
        },
        is_draft=True,
    )
    db.add(campaign)
    await db.flush()

    return {"id": campaign.id, "status": "draft_saved"}


@router.post("/approve-launch")
async def approve_and_launch(
    req: ApproveLaunchRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can launch campaigns")

    campaign = None

    # Case 1: Existing draft in DB
    if req.draft_campaign_id:
        result = await db.execute(
            select(Campaign).where(
                Campaign.id == req.draft_campaign_id,
                Campaign.tenant_id == user.tenant_id,
                Campaign.is_draft == True,
            )
        )
        campaign = result.scalar_one_or_none()

    # Case 2: Inline draft — auto-save then launch
    if not campaign and req.draft:
        from app.models.integration_google_ads import IntegrationGoogleAds
        acct_result = await db.execute(
            select(IntegrationGoogleAds).where(
                IntegrationGoogleAds.tenant_id == user.tenant_id,
                IntegrationGoogleAds.is_active == True,
                IntegrationGoogleAds.customer_id != "pending",
            ).limit(1)
        )
        account = acct_result.scalar_one_or_none()
        if not account:
            raise HTTPException(status_code=400, detail="No active Google Ads account")

        d = req.draft
        camp_data = d.get("campaign", {})
        campaign = Campaign(
            tenant_id=user.tenant_id,
            google_customer_id=account.customer_id,
            type=camp_data.get("type", "SEARCH"),
            name=camp_data.get("name", "AI Campaign"),
            status="DRAFT",
            objective=camp_data.get("objective", "leads"),
            budget_micros=camp_data.get("budget_micros", 30_000_000),
            bidding_strategy=camp_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
            settings_json={
                "locations": camp_data.get("locations", []),
                "schedule": camp_data.get("schedule", {}),
                "device_bids": camp_data.get("device_bids", {}),
                "network": camp_data.get("settings", {}).get("network", "SEARCH"),
                "ad_groups": d.get("ad_groups", []),
                "extensions": d.get("extensions", {}),
                "keyword_strategy": d.get("keyword_strategy", {}),
                "reasoning": d.get("reasoning", {}),
            },
            is_draft=True,
        )
        db.add(campaign)
        await db.flush()

    if not campaign:
        raise HTTPException(status_code=404, detail="Draft campaign not found — provide draft_campaign_id or inline draft")

    from app.jobs.tasks import launch_campaign_task
    launch_campaign_task.delay(user.tenant_id, campaign.id, user.user_id)

    campaign.status = "LAUNCHING"
    await db.flush()

    return {"id": campaign.id, "status": "launching"}
