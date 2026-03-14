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


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@router.post("/chat")
async def chat_refine(
    req: ChatRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """
    Multi-turn ChatGPT-style conversation for refining campaign prompts.
    The frontend sends the full conversation history and gets back the AI reply.
    The AI acts as a Google Ads strategist helping shape the perfect campaign brief.
    Every response includes a `draft_prompt` — the latest version of the campaign
    brief that would be sent to the generator if the user clicks Approve.
    """
    import json as _json
    from openai import AsyncOpenAI
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        return {
            "reply": "AI is not configured. Please type your full campaign brief and click Generate.",
            "draft_prompt": req.messages[-1].content if req.messages else "",
            "ready_to_generate": True,
        }

    # Gather business context
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()

    camp_result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == user.tenant_id).limit(20)
    )
    existing = camp_result.scalars().all()
    existing_names = [c.name for c in existing]

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
        svc_names, loc_names, offer_texts, usp_texts = [], [], [], []
        industry, phone, website, conversion_goal = "general", "", "", "calls"
        monthly_budget = 0

    system = f"""You are an expert Google Ads campaign strategist having a conversation
with a business owner. Your job is to help them build the perfect campaign brief
through natural conversation. You're friendly, knowledgeable, and proactive.

BUSINESS PROFILE (use this to give informed advice):
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

CONVERSATION RULES:
1. On the FIRST message, expand their rough idea into a clear campaign brief.
   Then ask 1-2 focused questions about things they might want to add or change.
2. On follow-up messages, incorporate their feedback and present the updated brief.
3. Keep your responses concise and conversational — NOT walls of text.
4. If they mention a niche service, keep it as the focus. Don't generalize.
5. Proactively suggest things from their business profile they forgot to mention
   (offers, USPs, locations).
6. Warn them if the new campaign might overlap with existing ones.
7. **LANDING PAGE QUESTION (CRITICAL):** Before you EVER set ready_to_generate to true,
   you MUST ask the user about their landing page. This is required. Ask them:
   "What about your landing page for this campaign?" and present these options:
   - **Use an existing landing page** — they'll enter their URL
   - **Create an AI-generated landing page** — we'll build one matched to the campaign
   - **Audit an existing landing page** — we'll score it for conversion quality
   - **Call-only ad (no landing page)** — for phone call campaigns with no website needed
   Include these as suggestions. Do NOT set ready_to_generate to true until the user
   has answered the landing page question. Once they answer, incorporate their choice
   into the brief and THEN set ready_to_generate to true.
8. When the brief feels complete AND the landing page question is answered,
   tell them it's ready and they can click Approve.

You MUST respond with valid JSON in this exact format:
{{
  "reply": "Your conversational response to the user (use markdown for formatting)",
  "draft_prompt": "The current version of the full campaign brief that would be sent to the generator. Update this every turn based on the conversation so far.",
  "ready_to_generate": true/false,
  "landing_page_choice": null | "existing" | "create_ai" | "audit" | "call_only",
  "landing_page_url": null | "https://...",
  "suggestions": ["optional quick-reply suggestion 1", "optional suggestion 2"]
}}

IMPORTANT NOTES:
- landing_page_choice should be null until the user picks a landing page option.
- landing_page_url should be set only if the user provides a URL for existing/audit.
- ready_to_generate must be false until the landing page question is answered.
- The draft_prompt should be a clean, detailed 2-5 sentence campaign brief — NOT your
  conversational reply. It's what gets fed to the campaign generator when they approve.
  Include the landing page choice in the draft_prompt once decided."""

    # Build OpenAI messages: system + conversation history
    openai_messages = [{"role": "system", "content": system}]
    for msg in req.messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=openai_messages,
            response_format={"type": "json_object"},
            temperature=0.6,
            max_tokens=1200,
        )
        content = response.choices[0].message.content
        if not content:
            return {
                "reply": "I couldn't generate a response. Please try again.",
                "draft_prompt": "",
                "ready_to_generate": False,
                "suggestions": [],
            }

        data = _json.loads(content)
        return {
            "reply": data.get("reply", ""),
            "draft_prompt": data.get("draft_prompt", ""),
            "ready_to_generate": data.get("ready_to_generate", False),
            "suggestions": data.get("suggestions", []),
            "landing_page_choice": data.get("landing_page_choice"),
            "landing_page_url": data.get("landing_page_url"),
        }
    except Exception as e:
        import structlog
        structlog.get_logger().error("Chat refinement failed", error=str(e))
        return {
            "reply": f"Something went wrong: {str(e)[:200]}. Please try again.",
            "draft_prompt": "",
            "ready_to_generate": False,
            "suggestions": [],
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
