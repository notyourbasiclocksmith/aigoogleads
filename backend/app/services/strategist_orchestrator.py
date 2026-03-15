"""
Strategist Orchestrator — The AI Marketing Operator brain.

Manages the fully-integrated campaign strategist chat flow:
  1. Parse intent from user prompt
  2. Ask about landing page (existing / audit / create AI page)
  3. Build campaign (+ LP if requested)
  4. AUTO-RUN AI audit on campaign + landing page
  5. AUTO-SUGGEST expansions: top 5/10/25 makes + related services
  6. One-click bulk generation from chat
  7. Surface search term mining insights in optimization flow
  8. Continuously recommend what else to build, improve, or expand

Integrates: CampaignGenerator, LandingPageGenerator, LandingPageAuditor,
CampaignAuditor, ExpansionScorer, ServiceExpander, SearchTermMiner.
"""
import json
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.business_profile import BusinessProfile as BPModel
from app.models.campaign import Campaign
from app.models.tenant import Tenant

logger = structlog.get_logger()


# Chat phases the orchestrator tracks
PHASE_INTENT = "intent_parsed"
PHASE_CAMPAIGN_TYPE = "campaign_type_decision"
PHASE_LP_DECISION = "landing_page_decision"
PHASE_GENERATING = "generating_campaign"
PHASE_CAMPAIGN_READY = "campaign_ready"
PHASE_LP_GENERATING = "generating_landing_page"
PHASE_LP_READY = "landing_page_ready"
PHASE_AUDITING = "auditing"
PHASE_AUDIT_DONE = "audit_complete"
PHASE_EXPANSION = "expansion_suggestions"
PHASE_BULK_LAUNCHED = "bulk_launched"
PHASE_OPTIMIZATION = "optimization"
PHASE_IDLE = "idle"


class StrategistOrchestrator:
    """
    Stateless orchestrator — receives full conversation + phase state,
    determines next action, executes it, returns response + updated state.

    Integrated flow:
      intent → LP decision → campaign build → AUTO audit → AUTO expansion →
      bulk generation → search term mining → continuous recommendations
    """

    # Action keys that quick-action buttons can send
    ACTION_MAP = {
        "type_call_only": "_action_type_call_only",
        "type_search": "_action_type_search",
        "type_pmax": "_action_type_pmax",
        "type_display": "_action_type_display",
        "lp_existing": "_action_lp_existing",
        "lp_create": "_action_lp_create",
        "lp_skip": "_action_lp_skip",
        "adjust": "_action_adjust",
        "generate_lp": "_action_generate_lp",
        "audit_campaign": "_action_audit_campaign",
        "audit_all": "_action_audit_all",
        "expand_makes": "_action_expand",
        "expand_services": "_action_expand",
        "expand": "_action_expand",
        "expand_5": "_action_bulk_expand",
        "expand_10": "_action_bulk_expand",
        "expand_25": "_action_bulk_expand",
        "expand_all": "_action_bulk_expand",
        "skip_expansion": "_action_skip_expansion",
        "bulk_10": "_action_bulk_from_expansion",
        "bulk_25": "_action_bulk_from_expansion",
        "bulk_50": "_action_bulk_from_expansion",
        "bulk_custom": "_action_bulk_from_expansion",
        "launch": "_action_launch",
        "new_campaign": "_action_new_campaign",
        "mine_search_terms": "_action_mine_search_terms",
        "optimize": "_action_optimize",
        "regenerate": "_action_regenerate",
        "what_next": "_action_what_next",
    }

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self._progress_queue = None  # optional asyncio.Queue for SSE streaming

    async def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        session_state: Dict[str, Any],
        action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point. Routes based on action key first, then phase + message.
        """
        phase = session_state.get("phase", "")
        profile = await self._load_profile()

        # ── Priority 1: explicit action from quick-action button ──
        if action and action in self.ACTION_MAP:
            handler_name = self.ACTION_MAP[action]
            handler = getattr(self, handler_name)
            return await handler(user_message, action, profile, session_state)

        # ── Priority 2: phase-based routing ──
        if not phase or phase == PHASE_IDLE:
            return await self._handle_intent_parsing(user_message, profile, session_state)

        elif phase == PHASE_INTENT:
            return await self._handle_post_intent(user_message, profile, session_state)

        elif phase == PHASE_CAMPAIGN_TYPE:
            return await self._handle_campaign_type_decision(user_message, profile, session_state)

        elif phase == PHASE_LP_DECISION:
            return await self._handle_lp_decision(user_message, profile, session_state)

        elif phase == PHASE_CAMPAIGN_READY:
            return await self._handle_post_campaign(user_message, profile, session_state)

        elif phase == PHASE_LP_READY:
            return await self._handle_post_lp(user_message, profile, session_state)

        elif phase == PHASE_AUDIT_DONE:
            return await self._handle_post_audit(user_message, profile, session_state)

        elif phase == PHASE_EXPANSION:
            return await self._handle_expansion_choice(user_message, profile, session_state)

        elif phase == PHASE_BULK_LAUNCHED:
            return await self._handle_post_bulk(user_message, profile, session_state)

        elif phase == PHASE_OPTIMIZATION:
            return await self._handle_optimization(user_message, profile, session_state)

        else:
            return await self._smart_route(user_message, conversation_history, profile, session_state)

    async def _load_profile(self) -> Optional[Dict]:
        result = await self.db.execute(
            select(BPModel).where(BPModel.tenant_id == self.tenant_id)
        )
        p = result.scalar_one_or_none()
        if not p:
            return None

        # Get business name from Tenant (not on BusinessProfile model)
        tenant_result = await self.db.execute(
            select(Tenant.name).where(Tenant.id == self.tenant_id)
        )
        tenant_name = tenant_result.scalar_one_or_none() or ""

        def _extract_list(raw) -> list:
            """Unwrap {"list": [...]} or {"cities": [...]} dict wrapper, or plain list."""
            if isinstance(raw, list):
                return raw
            if isinstance(raw, dict):
                for key in ("list", "cities", "items"):
                    if isinstance(raw.get(key), list):
                        return raw[key]
            return []

        services = _extract_list(p.services_json)
        svc_names = [s if isinstance(s, str) else s.get("name", "") for s in services]
        locations = _extract_list(p.locations_json)
        loc_names = [l if isinstance(l, str) else l.get("name", "") for l in locations]
        usps = _extract_list(p.usp_json)
        usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in usps]
        offers = _extract_list(p.offers_json)
        offer_texts = [o if isinstance(o, str) else o.get("text", "") for o in offers]

        # Trust signals — normalize from scanner dict or structured dict
        raw_ts = p.trust_signals_json if isinstance(p.trust_signals_json, dict) else {}
        ts_list = _extract_list(p.trust_signals_json)
        trust_signals_texts = [str(t) if isinstance(t, str) else t.get("text", str(t)) for t in ts_list]

        # Brand voice
        bv = p.brand_voice_json if isinstance(p.brand_voice_json, dict) else {}

        # Constraints (hours, emergency flag, etc.)
        constraints = p.constraints_json if isinstance(p.constraints_json, dict) else {}

        return {
            "business_name": tenant_name,
            "industry": p.industry_classification or "",
            "phone": p.phone or "",
            "website": p.website_url or "",
            "description": p.description or "",
            "services": svc_names,
            "locations": loc_names,
            "usps": usp_texts,
            "offers": offer_texts,
            "trust_signals": trust_signals_texts,
            "trust_signals_raw": raw_ts,
            "brand_voice": bv,
            "constraints": constraints,
            "conversion_goal": p.primary_conversion_goal or "calls",
        }

    # ── PHASE HANDLERS ────────────────────────────────────────────────

    async def _handle_intent_parsing(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Parse user's campaign idea into structured intent, then audit the
        response quality before sending.  Uses the AI-generated funnel
        recommendation instead of hardcoded rules."""
        intent = await self._parse_campaign_intent(message, profile)

        # ── Run response quality audit (second AI pass) ──────────────
        audited_intent = await self._audit_parsed_intent(intent, message, profile)
        if audited_intent:
            intent = audited_intent

        # ── Build rich reply ─────────────────────────────────────────
        reply_parts = [
            f"**Got it!** Here's what I understand:\n",
            f"- **Service:** {intent.get('service', 'N/A')}",
        ]
        if intent.get("service_category"):
            reply_parts.append(f"- **Category:** {intent['service_category']}")
        if intent.get("brand"):
            reply_parts.append(f"- **Brand/Make:** {intent['brand']}")
        reply_parts.extend([
            f"- **Location:** {intent.get('location', 'N/A')}",
            f"- **Industry:** {intent.get('industry', 'N/A')}",
            f"- **Goal:** {intent.get('goal', 'phone calls')}",
            f"- **Urgency:** {intent.get('urgency', 'standard')}",
        ])
        if intent.get("estimated_ticket_value"):
            reply_parts.append(f"- **Estimated Ticket Value:** {intent['estimated_ticket_value']}")
        if intent.get("customer_journey"):
            reply_parts.append(f"- **Customer Journey:** {intent['customer_journey']}")

        if intent.get("key_selling_points"):
            reply_parts.append(f"\n**Key selling points extracted:**")
            for usp in intent["key_selling_points"][:5]:
                reply_parts.append(f"- {usp}")

        if intent.get("related_services"):
            reply_parts.append(f"\n**Related services detected:** {', '.join(intent['related_services'][:5])}")
        if intent.get("expansion_potential"):
            reply_parts.append(f"**Expansion potential:** {', '.join(intent['expansion_potential'][:5])}")

        if intent.get("ad_angle"):
            reply_parts.append(f"\n**Ad angle:** {intent['ad_angle']}")

        if intent.get("competitive_insights"):
            reply_parts.append(f"**Competitive landscape:** {intent['competitive_insights']}")

        # ── AI-powered funnel recommendation (from the enhanced parse) ──
        funnel = intent.get("recommended_funnel")
        if funnel and isinstance(funnel, dict):
            reply_parts.append(f"\n---\n**Recommended Funnel: {funnel.get('type_label', funnel.get('type', 'N/A'))}**")
            reply_parts.append(f"**Why:** {funnel.get('reason', '')}")
            if funnel.get("alternative"):
                reply_parts.append(f"**Alternative:** {funnel['alternative']}")
        else:
            # Fallback if AI didn't include funnel
            funnel = self._recommend_funnel_fallback(intent)
            if funnel:
                intent["recommended_funnel"] = funnel
                reply_parts.append(f"\n---\n**Recommended Funnel: {funnel['type_label']}**")
                reply_parts.append(f"**Why:** {funnel['reason']}")

        # ── Quality self-audit warnings ──────────────────────────────
        quality = intent.get("quality_score", {})
        gaps = quality.get("gaps_found", [])
        missing_info = intent.get("missing_info", [])
        if missing_info:
            reply_parts.append(f"\n**To improve campaign quality, I'd also want to know:**")
            for mi in missing_info[:3]:
                reply_parts.append(f"- {mi}")

        # ── Negative keywords preview ────────────────────────────────
        neg_kws = intent.get("negative_keywords", [])
        if neg_kws:
            reply_parts.append(f"\n**Pre-loaded negative keywords:** {', '.join(neg_kws[:8])}")

        # ── If user pasted a landing page reference, note it ─────────
        lp_ref = intent.get("landing_page_reference_url")
        if lp_ref:
            reply_parts.append(
                f"\n**Landing page reference detected!** I'll use it as a reference "
                f"and audit it for campaign alignment."
            )
            state["landing_page_url"] = lp_ref

        # ── Campaign type selection ──────────────────────────────────
        # Determine which type the AI recommends so we can highlight it
        funnel_type = ""
        if funnel and isinstance(funnel, dict):
            funnel_type = funnel.get("type", "")

        reply_parts.append(
            "\n---\n**What type of campaign would you like to create?**"
        )

        # Build type descriptions with AI-recommended badge
        type_options = []
        rec_badge = " (Recommended)" if funnel_type == "call_only" else ""
        type_options.append(f"- **Call-Only Ad{rec_badge}** — Your phone number shows directly in the ad. No landing page needed. Best for emergencies and simple services.")

        rec_badge = " (Recommended)" if funnel_type in ("lp_call", "lp_form", "lp_booking") else ""
        type_options.append(f"- **Search Ad{rec_badge}** — Standard text ad that links to a landing page. Best for high-ticket services needing trust/explanation.")

        rec_badge = " (Recommended)" if funnel_type == "pmax" else ""
        type_options.append(f"- **Performance Max{rec_badge}** — AI-optimized across Search, Display, YouTube, Maps, and Gmail. Best for broad reach and brand awareness.")

        rec_badge = " (Recommended)" if funnel_type == "display" else ""
        type_options.append(f"- **Display Ad{rec_badge}** — Visual banner ads on websites. Best for remarketing and brand awareness.")

        reply_parts.extend(type_options)

        quick_actions = [
            {"label": "Call-Only Ad", "action": "type_call_only"},
            {"label": "Search Ad", "action": "type_search"},
            {"label": "Performance Max", "action": "type_pmax"},
            {"label": "Adjust Details", "action": "adjust"},
        ]

        return {
            "reply": "\n".join(reply_parts),
            "phase": PHASE_INTENT,
            "intent": intent,
            "quick_actions": quick_actions,
            "session_state": {**state, "phase": PHASE_INTENT, "intent": intent},
        }

    async def _audit_parsed_intent(
        self, intent: Dict, original_message: str, profile: Optional[Dict]
    ) -> Optional[Dict]:
        """Second AI pass: audit the parsed intent for quality and completeness.

        Reviews the extraction for:
        - Missed or misclassified information
        - Generic vs specific selling points
        - Keyword quality and coverage
        - Funnel recommendation appropriateness
        - Expansion opportunity realism

        Returns an improved intent dict, or None if audit is skipped/fails.
        """
        if not self.client:
            return None

        # Skip audit if the initial parse failed (no AI data)
        if not intent.get("_ai_parsed"):
            return None

        quality = intent.get("quality_score", {})
        overall_score = quality.get("overall", 10)
        # Skip audit if self-assessed quality is already high
        if overall_score >= 9 and not quality.get("gaps_found"):
            logger.info("Intent quality self-score high, skipping audit pass",
                        score=overall_score)
            return None

        system = """You are a senior QA reviewer for a Google Ads campaign strategist AI.
Your job is to audit another AI's campaign intent extraction and IMPROVE it.

You receive the original user message and the AI's parsed intent. You must:

1. CHECK ACCURACY — Is the service correctly identified? Is urgency right?
   Is the funnel recommendation appropriate for this specific service?
2. IMPROVE SPECIFICITY — Replace generic selling points with specific ones.
   Replace broad keywords with long-tail high-intent variants.
3. FIX GAPS — Add any missing information that's obviously implied.
4. VALIDATE FUNNEL — Is the recommended funnel actually the best choice?
   Consider: ticket value, urgency, customer sophistication, competition level.
5. ENHANCE EXPANSION — Are expansion suggestions realistic for this business
   type and geographic area?

Return the COMPLETE improved intent as valid JSON. Keep all original fields,
only modify what needs improvement. Add "_audit_improvements" listing changes."""

        audit_prompt = f"""ORIGINAL USER MESSAGE:
{original_message[:2000]}

AI'S PARSED INTENT:
{json.dumps({k: v for k, v in intent.items() if k != 'original_prompt'}, default=str, indent=2)[:3000]}

BUSINESS PROFILE:
{json.dumps(profile, default=str)[:800] if profile else 'None'}

Audit and improve this intent extraction. Return complete improved JSON."""

        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": audit_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2500,
                timeout=30,
            )
            content = resp.choices[0].message.content
            if content:
                audited = json.loads(content)
                # Preserve original prompt and AI flags
                audited["original_prompt"] = intent.get("original_prompt", original_message)
                audited["_ai_parsed"] = True
                audited["_audited"] = True
                improvements = audited.get("_audit_improvements", [])
                if improvements:
                    logger.info("Intent audit improved response",
                                improvements=len(improvements),
                                details=improvements[:3])
                return audited
        except Exception as e:
            logger.warning("Intent audit pass failed, using original",
                           error=str(e))

        return None

    def _recommend_funnel_fallback(self, intent: Dict) -> Optional[Dict]:
        """Rule-based funnel recommendation — used only when AI funnel is missing."""
        service = intent.get("service", "").lower()
        urgency = intent.get("urgency", "standard")
        goal = intent.get("goal", "phone calls")

        if urgency == "emergency":
            return {
                "type": "call_only",
                "type_label": "Call-Only Ad",
                "reason": "Emergency service — customers need help NOW and will call the first number they see.",
                "confidence": "high",
            }

        high_ticket_keywords = [
            "repair", "replacement", "remodel", "install", "module", "programming",
            "bcm", "kvm", "ecu", "frm", "esl", "airbag", "transmission", "engine",
            "hvac", "roof", "foundation", "commercial", "custom",
        ]
        if any(kw in service for kw in high_ticket_keywords):
            return {
                "type": "lp_call",
                "type_label": "Landing Page + Call",
                "reason": "High-ticket/complex service — a landing page builds trust before the call.",
                "confidence": "high",
            }

        if urgency == "research" or goal == "form leads":
            return {
                "type": "lp_form",
                "type_label": "Landing Page + Form",
                "reason": "Comparison-shopping customers prefer submitting info to multiple providers.",
                "confidence": "medium",
            }

        if goal == "bookings":
            return {
                "type": "lp_booking",
                "type_label": "Landing Page + Booking",
                "reason": "Appointment-based service — self-service scheduling increases conversion.",
                "confidence": "medium",
            }

        if goal == "phone calls":
            return {
                "type": "lp_call",
                "type_label": "Landing Page + Call",
                "reason": "Phone call campaigns benefit from a landing page that builds trust.",
                "confidence": "medium",
            }

        return None

    async def _handle_post_intent(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle response after intent parsing — campaign type selection or adjustment."""
        msg_lower = message.lower().strip()

        # Check if user wants to adjust
        if any(w in msg_lower for w in ["adjust", "change", "modify", "edit", "wrong", "no"]):
            return await self._handle_intent_parsing(message, profile, state)

        # Route campaign type selections from free text
        if any(w in msg_lower for w in ["call only", "call-only", "phone ad"]):
            return await self._action_type_call_only(message, "type_call_only", profile, state)
        elif any(w in msg_lower for w in ["search ad", "search campaign", "text ad"]):
            return await self._action_type_search(message, "type_search", profile, state)
        elif any(w in msg_lower for w in ["performance max", "pmax", "p-max"]):
            return await self._action_type_pmax(message, "type_pmax", profile, state)
        elif any(w in msg_lower for w in ["display", "banner"]):
            return await self._action_type_display(message, "type_display", profile, state)

        # Default: re-show the campaign type options
        return self._reply(
            "Please select a campaign type above, or tell me which type you'd like:\n\n"
            "- **Call-Only Ad** — phone number in the ad, no landing page needed\n"
            "- **Search Ad** — text ad with landing page\n"
            "- **Performance Max** — AI-optimized across all Google channels\n"
            "- **Display Ad** — visual banner ads",
            PHASE_INTENT, state,
            quick_actions=[
                {"label": "Call-Only Ad", "action": "type_call_only"},
                {"label": "Search Ad", "action": "type_search"},
                {"label": "Performance Max", "action": "type_pmax"},
                {"label": "Adjust Details", "action": "adjust"},
            ],
        )

    # ── CAMPAIGN TYPE ACTION HANDLERS ─────────────────────────────────

    async def _action_type_call_only(
        self, msg: str, action: str, profile: Optional[Dict], state: Dict
    ) -> Dict:
        """Call-Only selected — no landing page needed, go straight to build."""
        state["campaign_type"] = "CALL"
        state["lp_choice"] = "skip"
        intent = state.get("intent", {})
        intent["campaign_type_override"] = "CALL"
        state["intent"] = intent

        reply = (
            "**Call-Only Ad selected!**\n\n"
            "No landing page needed — your phone number will show directly in the ad. "
            "Customers tap to call instantly.\n\n"
            "Building your campaign now..."
        )
        draft = await self._generate_campaign_only(profile, state)
        reply += f"\n\n{self._format_draft_summary(draft)}\n\n"
        if draft.get("error"):
            reply += f"\n\u26a0\ufe0f {draft['error']}"
        reply += "**What would you like to do next?**"

        state["phase"] = PHASE_CAMPAIGN_READY
        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_READY,
            "campaign_draft": draft,
            "session_state": state,
            "quick_actions": [
                {"label": "Audit Campaign", "action": "audit_campaign"},
                {"label": "Find Expansions", "action": "expand"},
                {"label": "Approve & Launch", "action": "launch"},
                {"label": "Build Another Campaign", "action": "new_campaign"},
            ],
        }

    async def _action_type_search(
        self, msg: str, action: str, profile: Optional[Dict], state: Dict
    ) -> Dict:
        """Search Ad selected — needs a landing page, ask about it."""
        state["campaign_type"] = "SEARCH"
        intent = state.get("intent", {})
        intent["campaign_type_override"] = "SEARCH"
        state["intent"] = intent
        state["phase"] = PHASE_CAMPAIGN_TYPE

        # Check if they already provided an LP reference
        if state.get("landing_page_url"):
            reply = (
                "**Search Ad selected!**\n\n"
                f"I see you already provided a landing page reference. "
                f"Would you like me to audit it, or create an AI-optimized page?"
            )
            return {
                "reply": reply,
                "phase": PHASE_CAMPAIGN_TYPE,
                "session_state": state,
                "quick_actions": [
                    {"label": "Audit & Use This Page", "action": "lp_existing"},
                    {"label": "Create AI Landing Page", "action": "lp_create"},
                    {"label": "Skip Landing Page", "action": "lp_skip"},
                ],
            }

        reply = (
            "**Search Ad selected!**\n\n"
            "Search ads need a landing page to drive traffic to. "
            "A good landing page can **double your conversion rate**.\n\n"
            "**Do you have a landing page for this service?**"
        )
        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_TYPE,
            "session_state": state,
            "quick_actions": [
                {"label": "Use Existing Landing Page", "action": "lp_existing"},
                {"label": "Create AI Landing Page", "action": "lp_create"},
                {"label": "Skip Landing Page", "action": "lp_skip"},
            ],
        }

    async def _action_type_pmax(
        self, msg: str, action: str, profile: Optional[Dict], state: Dict
    ) -> Dict:
        """Performance Max selected — ask about assets/LP."""
        state["campaign_type"] = "PERFORMANCE_MAX"
        intent = state.get("intent", {})
        intent["campaign_type_override"] = "PERFORMANCE_MAX"
        state["intent"] = intent
        state["phase"] = PHASE_CAMPAIGN_TYPE

        reply = (
            "**Performance Max selected!**\n\n"
            "PMax campaigns run across Search, Display, YouTube, Gmail, and Maps — "
            "Google's AI optimizes placement automatically.\n\n"
            "A landing page is **highly recommended** for PMax to maximize conversions.\n\n"
            "**Do you have a landing page for this service?**"
        )
        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_TYPE,
            "session_state": state,
            "quick_actions": [
                {"label": "Use Existing Landing Page", "action": "lp_existing"},
                {"label": "Create AI Landing Page", "action": "lp_create"},
                {"label": "Skip Landing Page", "action": "lp_skip"},
            ],
        }

    async def _action_type_display(
        self, msg: str, action: str, profile: Optional[Dict], state: Dict
    ) -> Dict:
        """Display Ad selected — needs LP and creative assets."""
        state["campaign_type"] = "DISPLAY"
        intent = state.get("intent", {})
        intent["campaign_type_override"] = "DISPLAY"
        state["intent"] = intent
        state["phase"] = PHASE_CAMPAIGN_TYPE

        reply = (
            "**Display Ad selected!**\n\n"
            "Display ads show visual banners across the Google Display Network. "
            "Great for remarketing and brand awareness.\n\n"
            "A landing page is **required** for Display campaigns.\n\n"
            "**Do you have a landing page for this service?**"
        )
        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_TYPE,
            "session_state": state,
            "quick_actions": [
                {"label": "Use Existing Landing Page", "action": "lp_existing"},
                {"label": "Create AI Landing Page", "action": "lp_create"},
                {"label": "Skip Landing Page", "action": "lp_skip"},
            ],
        }

    async def _handle_campaign_type_decision(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle free-text response to campaign type / LP question in PHASE_CAMPAIGN_TYPE."""
        msg_lower = message.lower().strip()

        # Route LP choices from free text
        if any(w in msg_lower for w in ["existing", "have a page", "url", "my page", "yes"]):
            return await self._action_lp_existing(message, "lp_existing", profile, state)
        elif any(w in msg_lower for w in ["create", "generate", "ai page", "build page", "new page"]):
            return await self._action_lp_create(message, "lp_create", profile, state)
        elif any(w in msg_lower for w in ["skip", "no page", "don't have", "no lp", "no landing"]):
            return await self._action_lp_skip(message, "lp_skip", profile, state)
        elif message.strip().startswith("http"):
            # User pasted a URL directly
            state["landing_page_url"] = message.strip()
            return await self._action_lp_existing(message, "lp_existing", profile, state)

        # Default: re-prompt
        return self._reply(
            "Please choose a landing page option:\n\n"
            "- **Use Existing** — paste your landing page URL and I'll audit it\n"
            "- **Create AI Page** — I'll build a conversion-optimized page\n"
            "- **Skip** — proceed without a landing page",
            PHASE_CAMPAIGN_TYPE, state,
            quick_actions=[
                {"label": "Use Existing Landing Page", "action": "lp_existing"},
                {"label": "Create AI Landing Page", "action": "lp_create"},
                {"label": "Skip Landing Page", "action": "lp_skip"},
            ],
        )

    async def _handle_lp_decision(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle LP URL input or other LP decisions."""
        lp_choice = state.get("lp_choice", "skip")

        if lp_choice == "existing" and message.strip().startswith("http"):
            state["landing_page_url"] = message.strip()

        # Just build the campaign — don't chain audit+expansion in one request
        draft = await self._generate_campaign_only(profile, state)
        reply = f"**Campaign Built!**\n\n{self._format_draft_summary(draft)}\n\n"
        if state.get("landing_page_url"):
            reply += f"\u2705 Landing page URL saved: `{state['landing_page_url']}`\n\n"
        reply += "**What would you like to do next?**"
        state["phase"] = PHASE_CAMPAIGN_READY

        actions = []
        if state.get("landing_page_url"):
            actions.append({"label": "Audit Landing Page", "action": "audit_all"})
        actions.extend(self._post_campaign_actions())

        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_READY,
            "campaign_draft": draft,
            "session_state": state,
            "quick_actions": actions,
        }

    async def _handle_post_campaign(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle actions after campaign is built."""
        msg_lower = message.lower().strip()

        if any(w in msg_lower for w in ["landing page", "create page", "generate page", "build page", "lp"]):
            return await self._trigger_landing_page_gen(profile, state)
        elif any(w in msg_lower for w in ["audit", "check", "review", "score"]):
            return await self._trigger_full_audit(profile, state)
        elif any(w in msg_lower for w in ["expand", "similar", "more makes", "related", "grow"]):
            return await self._trigger_expansion(profile, state)
        elif any(w in msg_lower for w in ["search term", "mining", "search report"]):
            return await self._trigger_search_term_mining(profile, state)
        elif any(w in msg_lower for w in ["bulk", "batch", "multiple", "mass"]):
            return await self._trigger_expansion(profile, state)
        elif any(w in msg_lower for w in ["launch", "approve", "go live"]):
            return self._reply(
                "Campaign is ready to launch! Click **Approve & Launch** to push it to Google Ads.",
                PHASE_CAMPAIGN_READY, state,
                quick_actions=self._post_campaign_actions(),
            )
        else:
            return await self._smart_route(message, [], profile, state)

    async def _handle_post_lp(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle actions after landing page is built — auto-audit everything."""
        return await self._trigger_full_audit(profile, state)

    async def _handle_post_audit(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle actions after audits are complete — auto-suggest expansions."""
        return await self._trigger_expansion(profile, state)

    async def _handle_expansion_choice(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle expansion selection (top 5, top 10, etc.)."""
        msg_lower = message.lower().strip()
        expansions = state.get("expansions", [])

        count = 5
        if "10" in msg_lower or "ten" in msg_lower:
            count = 10
        elif "25" in msg_lower or "twenty" in msg_lower:
            count = 25
        elif "50" in msg_lower or "fifty" in msg_lower:
            count = 50
        elif "all" in msg_lower:
            count = len(expansions)
        elif "skip" in msg_lower or "no" in msg_lower:
            return await self._continuous_recommendation(profile, state)

        return self._launch_bulk(expansions[:count], state)

    async def _handle_post_bulk(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """After bulk generation launched, offer optimization and continuous recs."""
        msg_lower = message.lower().strip()

        if any(w in msg_lower for w in ["search term", "mining", "optimize"]):
            return await self._trigger_search_term_mining(profile, state)
        elif any(w in msg_lower for w in ["new", "another", "build"]):
            return await self._handle_intent_parsing(message, profile, {**state, "phase": ""})
        else:
            return await self._continuous_recommendation(profile, state)

    async def _handle_optimization(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle optimization flow — search term mining results are in state."""
        msg_lower = message.lower().strip()

        if any(w in msg_lower for w in ["build", "new", "campaign", "another"]):
            return await self._handle_intent_parsing(message, profile, {**state, "phase": ""})
        elif any(w in msg_lower for w in ["expand", "more", "grow"]):
            return await self._trigger_expansion(profile, state)
        elif any(w in msg_lower for w in ["audit", "check"]):
            return await self._trigger_full_audit(profile, state)
        else:
            return await self._continuous_recommendation(profile, state)

    # ── QUICK-ACTION HANDLERS ──────────────────────────────────────────

    async def _action_lp_existing(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return self._reply(
            "Please paste the URL of your existing landing page and I'll **audit it** for campaign alignment before building.",
            PHASE_LP_DECISION, state, lp_choice="existing",
        )

    async def _action_lp_create(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        state["lp_choice"] = "create"
        # Step 1: Just build the campaign first (don't chain everything)
        draft = await self._generate_campaign_only(profile, state)
        reply = f"**Campaign Built!**\n\n{self._format_draft_summary(draft)}\n\n"
        if draft.get("error"):
            return self._reply(
                reply + f"\n⚠️ {draft['error']}",
                PHASE_CAMPAIGN_READY, state,
                campaign_draft=draft,
                quick_actions=self._post_campaign_actions(),
            )
        reply += "---\n\nNow I'll **generate your AI landing page**. Click below to continue."
        state["phase"] = PHASE_CAMPAIGN_READY
        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_READY,
            "campaign_draft": draft,
            "session_state": state,
            "quick_actions": [
                {"label": "Generate Landing Page Now", "action": "generate_lp"},
                {"label": "Audit Campaign First", "action": "audit_campaign"},
                {"label": "Skip LP — Launch Campaign", "action": "launch"},
            ],
        }

    async def _action_lp_skip(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        state["lp_choice"] = "skip"
        # Step 1: Just build the campaign (don't chain audit+expansion)
        draft = await self._generate_campaign_only(profile, state)
        reply = f"**Campaign Built!**\n\n{self._format_draft_summary(draft)}\n\n"
        if draft.get("error"):
            return self._reply(
                reply + f"\n⚠️ {draft['error']}",
                PHASE_CAMPAIGN_READY, state,
                campaign_draft=draft,
                quick_actions=self._post_campaign_actions(),
            )
        reply += "**What would you like to do next?**"
        state["phase"] = PHASE_CAMPAIGN_READY
        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_READY,
            "campaign_draft": draft,
            "session_state": state,
            "quick_actions": self._post_campaign_actions(),
        }

    async def _action_adjust(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return self._reply(
            "Sure! Tell me what to change — service, location, brand, urgency, or goal — and I'll re-parse your campaign intent.",
            PHASE_IDLE, state,
        )

    async def _action_generate_lp(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._trigger_landing_page_gen(profile, state)

    async def _action_audit_campaign(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._trigger_full_audit(profile, state)

    async def _action_audit_all(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._trigger_full_audit(profile, state)

    async def _action_expand(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._trigger_expansion(profile, state)

    async def _action_bulk_expand(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        expansions = state.get("expansions", [])
        count_map = {"expand_5": 5, "expand_10": 10, "expand_25": 25, "expand_all": len(expansions)}
        count = count_map.get(action, 5)
        return self._launch_bulk(expansions[:count], state)

    async def _action_skip_expansion(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._continuous_recommendation(profile, state)

    async def _action_bulk_from_expansion(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        expansions = state.get("expansions", [])
        count_map = {"bulk_10": 10, "bulk_25": 25, "bulk_50": 50, "bulk_custom": len(expansions)}
        count = count_map.get(action, 10)
        return self._launch_bulk(expansions[:count], state)

    async def _action_launch(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return self._reply(
            "Campaign approved! Click **Launch** in the campaign preview panel to push it to Google Ads.\n\n"
            "While it syncs, I recommend setting up **search term mining** to start optimizing as soon as data flows in.",
            PHASE_CAMPAIGN_READY, state,
            quick_actions=[
                {"label": "Mine Search Terms", "action": "mine_search_terms"},
                {"label": "Build Another Campaign", "action": "new_campaign"},
                {"label": "What Should I Do Next?", "action": "what_next"},
            ],
        )

    async def _action_new_campaign(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return self._reply(
            "Let's build another campaign! **Describe the service, location, and audience** and I'll get started.",
            PHASE_IDLE, {**state, "phase": PHASE_IDLE},
        )

    async def _action_mine_search_terms(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._trigger_search_term_mining(profile, state)

    async def _action_optimize(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._trigger_search_term_mining(profile, state)

    async def _action_regenerate(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        state["phase"] = ""
        intent = state.get("intent", {})
        prompt = intent.get("original_prompt", intent.get("service", ""))
        return await self._handle_intent_parsing(prompt, profile, state)

    async def _action_what_next(self, msg: str, action: str, profile: Optional[Dict], state: Dict) -> Dict:
        return await self._continuous_recommendation(profile, state)

    # ── CORE ACTION TRIGGERS ──────────────────────────────────────────

    async def _get_bp_obj(self):
        """Load the ORM BusinessProfile object."""
        bp_result = await self.db.execute(
            select(BPModel).where(BPModel.tenant_id == self.tenant_id)
        )
        return bp_result.scalar_one_or_none()

    async def _generate_campaign_only(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Build campaign — returns draft dict and updates state."""
        intent = state.get("intent", {})
        from app.services.campaign_generator import CampaignGeneratorService

        prompt = intent.get("original_prompt", intent.get("service", ""))
        campaign_type_override = intent.get("campaign_type_override") or state.get("campaign_type")
        generator = CampaignGeneratorService(self.db, self.tenant_id)
        bp_obj = await self._get_bp_obj()

        if bp_obj:
            draft = await generator.generate_from_prompt(
                prompt, bp_obj, campaign_type_override=campaign_type_override,
                progress_queue=self._progress_queue,
            )
        else:
            draft = {
                "campaign": {"name": intent.get("service", "Campaign")},
                "ad_groups": [],
                "error": "No business profile found. Please complete onboarding first.",
            }

        state["campaign_draft"] = draft
        state["phase"] = PHASE_CAMPAIGN_READY
        return draft

    def _format_draft_summary(self, draft: Dict) -> str:
        """Format a campaign draft into a readable summary — adapts to campaign type."""
        camp = draft.get("campaign", {})
        camp_type = (camp.get("type") or "SEARCH").upper()
        lines = [f"- **Campaign:** {camp.get('name', 'N/A')}"]
        lines.append(f"- **Type:** {camp_type}")
        lines.append(f"- **Budget:** ${camp.get('budget_daily_usd', 0)}/day (${camp.get('budget_monthly_estimate_usd', 0)}/mo est.)")
        lines.append(f"- **Bidding:** {camp.get('bidding_strategy', 'N/A')}")

        if camp_type == "PERFORMANCE_MAX":
            ag_count = len(draft.get("asset_groups", []))
            lines.append(f"- **Asset Groups:** {ag_count}")
            for ag in draft.get("asset_groups", []):
                ta = ag.get("text_assets", {})
                lines.append(f"  - {ag.get('name', '?')}: {len(ta.get('headlines', []))} headlines, {len(ta.get('descriptions', []))} descriptions")
        else:
            ag_count = len(draft.get("ad_groups", []))
            kw_count = sum(len(ag.get("keywords", [])) for ag in draft.get("ad_groups", []))
            ad_count = sum(len(ag.get("ads", [])) for ag in draft.get("ad_groups", []))
            lines.append(f"- **Ad Groups:** {ag_count}")
            if kw_count:
                lines.append(f"- **Keywords:** {kw_count}")
            lines.append(f"- **Ads:** {ad_count}")
            if camp_type == "CALL":
                lines.append(f"- **Phone:** {camp.get('settings', {}).get('phone_number', 'N/A')}")
            elif camp_type == "DISPLAY":
                lines.append("- **Targeting:** Audience-based (in-market + custom intent)")

        # Compliance score
        compliance = draft.get("compliance", {})
        if not compliance:
            compliance = draft.get("ai_analysis", {}).get("compliance", {})
        if compliance.get("score") is not None:
            grade = compliance.get("grade", "N/A")
            score = compliance.get("score", 0)
            grade_emoji = {"EXCELLENT": "🟢", "GOOD": "🟡", "AVERAGE": "🟠", "POOR": "🔴"}.get(grade, "⚪")
            lines.append(f"- **Google Ad Strength:** {grade_emoji} {grade} ({score}/100)")
            if compliance.get("critical", 0) > 0:
                lines.append(f"  - ⚠️ {compliance['critical']} critical issue(s) remaining")

        # Builder log summary
        builder_log = draft.get("builder_log", {})
        steps = builder_log.get("steps", [])
        if steps:
            total_sec = builder_log.get("total_elapsed_sec", 0)
            lines.append(f"\n**🔧 AI Builder Log** ({len(steps)} steps, {total_sec}s total):")
            for s in steps:
                status_icon = {"done": "✅", "error": "❌", "running": "⏳"}.get(s.get("status"), "⚪")
                elapsed = s.get("elapsed_ms")
                time_str = f" ({elapsed}ms)" if elapsed is not None else ""
                lines.append(f"  {status_icon} **{s['step']}**{time_str} — {s.get('result_summary') or s.get('detail', '')}")

        reasoning = draft.get("reasoning", {})
        if reasoning.get("campaign_type"):
            lines.append(f"\n> {reasoning['campaign_type']}")

        return "\n".join(lines)

    async def _build_campaign_and_auto_audit(self, profile: Optional[Dict], state: Dict) -> Dict:
        """
        Build campaign → auto-run campaign audit → auto-suggest expansions.
        This is the core integrated flow.
        """
        # Step 1: Build campaign
        draft = await self._generate_campaign_only(profile, state)
        reply = f"**Campaign Built!**\n\n{self._format_draft_summary(draft)}\n\n"

        if draft.get("error"):
            return self._reply(
                reply + f"\n⚠️ {draft['error']}",
                PHASE_CAMPAIGN_READY, state,
                campaign_draft=draft,
                quick_actions=self._post_campaign_actions(),
            )

        # Step 2: Auto-audit the campaign
        reply += "---\n\n**Running AI quality audit...**\n\n"
        audit_data = await self._run_campaign_audit(state)
        campaign_audit = audit_data.get("campaign_audit", {})
        reply += self._format_audit_summary(campaign_audit)

        # Step 3: Auto-suggest expansions
        reply += "\n\n---\n\n**Scanning for expansion opportunities...**\n\n"
        expansion_data = await self._run_expansion(profile, state)
        expansions = expansion_data.get("expansions", [])
        reply += self._format_expansion_summary(expansion_data)

        if expansions:
            reply += "\n\n**How many expansion campaigns would you like me to generate?**"
            state["phase"] = PHASE_EXPANSION
            return {
                "reply": reply,
                "phase": PHASE_EXPANSION,
                "campaign_draft": draft,
                "campaign_audit": campaign_audit,
                "expansions": expansions,
                "session_state": state,
                "quick_actions": [
                    {"label": "Generate Top 5 Makes", "action": "expand_5"},
                    {"label": "Generate Top 10 Makes", "action": "expand_10"},
                    {"label": "Generate Top 25 Makes", "action": "expand_25"},
                    {"label": "Generate All + Landing Pages", "action": "expand_all"},
                    {"label": "Skip — Launch This One", "action": "launch"},
                    {"label": "Generate Landing Page First", "action": "generate_lp"},
                ],
            }

        # No expansions found — go to campaign ready
        reply += "\n\n**Your campaign is ready!** What would you like to do next?"
        return self._reply(
            reply, PHASE_CAMPAIGN_READY, state,
            campaign_draft=draft,
            campaign_audit=campaign_audit,
            quick_actions=self._post_campaign_actions(),
        )

    async def _build_campaign_lp_audit_expand(self, profile: Optional[Dict], state: Dict) -> Dict:
        """
        Full pipeline: campaign → landing page → audit both → expansions.
        """
        # Step 1: Build campaign
        draft = await self._generate_campaign_only(profile, state)
        reply = f"**Campaign Built!**\n\n{self._format_draft_summary(draft)}\n\n"

        # Step 2: Generate landing page
        reply += "---\n\n**Generating AI landing page with 3 variants...**\n\n"
        lp_data = await self._run_landing_page_gen(profile, state)
        landing_page = lp_data.get("landing_page", {})
        if landing_page.get("error"):
            reply += f"⚠️ Landing page generation failed: {landing_page['error']}\n\n"
        else:
            variants = landing_page.get("variants", [])
            for v in variants:
                reply += f"- **Variant {v.get('key', '?')}** — {v.get('name', '')}\n"
            reply += f"\nPage slug: `{landing_page.get('slug', '')}`\n\n"

        # Step 3: Auto-audit campaign
        reply += "---\n\n**Running AI quality audit...**\n\n"
        audit_data = await self._run_campaign_audit(state)
        campaign_audit = audit_data.get("campaign_audit", {})
        reply += self._format_audit_summary(campaign_audit)

        # Step 4: Audit landing page if URL exists
        if state.get("landing_page_url"):
            lp_audit = await self._run_lp_audit(state)
            reply += f"\n\n**Landing Page Audit:** {lp_audit.get('overall_score', 0)}/100\n"

        # Step 5: Auto-suggest expansions
        reply += "\n\n---\n\n**Scanning for expansion opportunities...**\n\n"
        expansion_data = await self._run_expansion(profile, state)
        expansions = expansion_data.get("expansions", [])
        reply += self._format_expansion_summary(expansion_data)

        if expansions:
            reply += "\n\n**How many expansion campaigns would you like me to generate?**"
            state["phase"] = PHASE_EXPANSION
            return {
                "reply": reply,
                "phase": PHASE_EXPANSION,
                "campaign_draft": draft,
                "landing_page": landing_page,
                "campaign_audit": campaign_audit,
                "expansions": expansions,
                "session_state": state,
                "quick_actions": [
                    {"label": "Generate Top 5 Makes", "action": "expand_5"},
                    {"label": "Generate Top 10 Makes", "action": "expand_10"},
                    {"label": "Generate Top 25 Makes", "action": "expand_25"},
                    {"label": "Generate All + Landing Pages", "action": "expand_all"},
                    {"label": "Skip — Launch This One", "action": "launch"},
                ],
            }

        return self._reply(
            reply + "\n\n**Campaign + landing page are ready!**",
            PHASE_LP_READY, state,
            campaign_draft=draft, landing_page=landing_page, campaign_audit=campaign_audit,
            quick_actions=[
                {"label": "Approve & Launch", "action": "launch"},
                {"label": "Mine Search Terms", "action": "mine_search_terms"},
                {"label": "Build Another Campaign", "action": "new_campaign"},
            ],
        )

    async def _generate_campaign_with_audit(self, url: str, profile: Optional[Dict], state: Dict) -> Dict:
        """Build campaign + audit existing landing page + auto-audit + expansions."""
        # Step 1: Build campaign
        draft = await self._generate_campaign_only(profile, state)
        reply = f"**Campaign Built!**\n\n{self._format_draft_summary(draft)}\n\n"

        # Step 2: Audit the existing landing page
        from app.services.landing_page_auditor import LandingPageAuditor
        intent = state.get("intent", {})
        auditor = LandingPageAuditor(self.db, self.tenant_id)
        lp_audit = await auditor.audit_url(
            url=url,
            campaign_keywords=intent.get("suggested_keywords", []),
            service=intent.get("service", ""),
            location=intent.get("location", ""),
        )
        state["lp_audit"] = lp_audit

        score = lp_audit.get("overall_score", 0)
        grade = lp_audit.get("grade", "?")
        reply += f"---\n\n**Landing Page Audit: {score}/100 ({grade})**\n\n"
        for issue in lp_audit.get("top_issues", [])[:3]:
            reply += f"- {issue}\n"
        if lp_audit.get("top_recommendations"):
            reply += "\n**Recommendations:**\n"
            for rec in lp_audit["top_recommendations"][:3]:
                reply += f"- {rec}\n"

        if score < 70:
            reply += "\n⚠️ **Your page scored below 70.** I recommend creating an AI-optimized landing page.\n"

        # Step 3: Auto-audit campaign
        reply += "\n---\n\n**Campaign Quality Audit:**\n\n"
        audit_data = await self._run_campaign_audit(state)
        campaign_audit = audit_data.get("campaign_audit", {})
        reply += self._format_audit_summary(campaign_audit)

        # Step 4: Auto-expansions
        reply += "\n\n---\n\n**Expansion Opportunities:**\n\n"
        expansion_data = await self._run_expansion(profile, state)
        expansions = expansion_data.get("expansions", [])
        reply += self._format_expansion_summary(expansion_data)

        actions = []
        if score < 70:
            actions.append({"label": "Create AI Landing Page Instead", "action": "generate_lp"})

        if expansions:
            reply += "\n\n**How many expansion campaigns would you like?**"
            state["phase"] = PHASE_EXPANSION
            actions.extend([
                {"label": "Generate Top 5 Makes", "action": "expand_5"},
                {"label": "Generate Top 10 Makes", "action": "expand_10"},
                {"label": "Generate Top 25 Makes", "action": "expand_25"},
                {"label": "Skip — Launch This One", "action": "launch"},
            ])
            return {
                "reply": reply,
                "phase": PHASE_EXPANSION,
                "campaign_draft": draft, "lp_audit": lp_audit,
                "campaign_audit": campaign_audit, "expansions": expansions,
                "session_state": state, "quick_actions": actions,
            }

        actions.extend(self._post_campaign_actions())
        return self._reply(
            reply, PHASE_CAMPAIGN_READY, state,
            campaign_draft=draft, lp_audit=lp_audit, campaign_audit=campaign_audit,
            quick_actions=actions,
        )

    # ── SUB-AGENT RUNNERS ─────────────────────────────────────────────

    async def _run_campaign_audit(self, state: Dict) -> Dict:
        """Run campaign auditor and store result in state."""
        from app.services.campaign_auditor import CampaignAuditor
        draft = state.get("campaign_draft", {})
        auditor = CampaignAuditor(self.db, self.tenant_id)
        audit = await auditor.audit_draft(draft)
        state["campaign_audit"] = audit
        return {"campaign_audit": audit}

    async def _run_lp_audit(self, state: Dict) -> Dict:
        """Run LP auditor on state's landing_page_url."""
        from app.services.landing_page_auditor import LandingPageAuditor
        intent = state.get("intent", {})
        url = state.get("landing_page_url", "")
        auditor = LandingPageAuditor(self.db, self.tenant_id)
        audit = await auditor.audit_url(
            url=url,
            campaign_keywords=intent.get("suggested_keywords", []),
            service=intent.get("service", ""),
            location=intent.get("location", ""),
        )
        state["lp_audit"] = audit
        return audit

    async def _run_expansion(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Run expansion scorer and store in state."""
        from app.services.expansion_scorer import ExpansionScorer
        intent = state.get("intent", {})
        draft = state.get("campaign_draft", {})
        scorer = ExpansionScorer(self.db, self.tenant_id)
        result = await scorer.score_expansions(
            source_campaign_name=draft.get("campaign", {}).get("name", ""),
            service=intent.get("service", ""),
            location=intent.get("location", ""),
            industry=intent.get("industry", ""),
        )
        state["expansions"] = result.get("expansions", [])
        return result

    async def _run_landing_page_gen(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Generate landing page and store in state."""
        from app.services.landing_page_generator import LandingPageGenerator
        intent = state.get("intent", {})
        draft = state.get("campaign_draft", {})
        keywords, headlines = [], []
        for ag in draft.get("ad_groups", []):
            for kw in ag.get("keywords", []):
                keywords.append(kw.get("text", kw) if isinstance(kw, dict) else kw)
            for ad in ag.get("ads", []):
                headlines.extend(ad.get("headlines", []))
        gen = LandingPageGenerator(self.db, self.tenant_id)
        lp = await gen.generate(
            service=intent.get("service", ""),
            location=intent.get("location", ""),
            industry=intent.get("industry", ""),
            business_name=profile.get("business_name", "") if profile else "",
            phone=profile.get("phone", "") if profile else "",
            website=profile.get("website", "") if profile else "",
            usps=profile.get("usps", []) if profile else [],
            offers=profile.get("offers", []) if profile else [],
            campaign_keywords=keywords[:20],
            campaign_headlines=headlines[:10],
            trust_signals=profile.get("trust_signals", []) if profile else [],
            description=profile.get("description", "") if profile else "",
            constraints=profile.get("constraints", {}) if profile else {},
        )
        state["landing_page"] = lp
        return {"landing_page": lp}

    async def _run_search_term_mining(self, state: Dict) -> Dict:
        """Run search term mining and return summary."""
        from app.services.search_term_miner import SearchTermMiner
        from app.models.integration_google_ads import IntegrationGoogleAds

        # Get the Google customer ID
        int_result = await self.db.execute(
            select(IntegrationGoogleAds.google_customer_id).where(
                IntegrationGoogleAds.tenant_id == self.tenant_id
            ).limit(1)
        )
        row = int_result.first()
        if not row:
            return {"status": "no_account", "message": "No Google Ads account connected."}

        miner = SearchTermMiner(self.db, self.tenant_id)
        result = await miner.mine(row.google_customer_id, days=30)
        state["search_mining"] = result
        return result

    # ── TRIGGER HELPERS (called from phase handlers) ──────────────────

    async def _trigger_landing_page_gen(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Generate landing page then auto-audit."""
        lp_data = await self._run_landing_page_gen(profile, state)
        lp = lp_data.get("landing_page", {})
        state["phase"] = PHASE_LP_READY

        if lp.get("error"):
            return self._reply(
                f"Landing page generation failed: {lp['error']}",
                PHASE_CAMPAIGN_READY, state,
            )

        variants = lp.get("variants", [])
        reply = "**Landing Page Generated!** 3 variants ready:\n\n"
        for v in variants:
            reply += f"- **Variant {v.get('key', '?')}** — {v.get('name', '')}\n"
        reply += f"\nSlug: `{lp.get('slug', '')}`"

        reply += "\n\n---\n\n**Auto-running quality audit...**\n\n"
        audit_data = await self._run_campaign_audit(state)
        campaign_audit = audit_data.get("campaign_audit", {})
        reply += self._format_audit_summary(campaign_audit)
        state["phase"] = PHASE_AUDIT_DONE

        reply += "\n\n**Ready to find expansion opportunities?**"

        return {
            "reply": reply,
            "phase": PHASE_AUDIT_DONE,
            "landing_page": lp, "campaign_audit": campaign_audit,
            "session_state": state,
            "quick_actions": [
                {"label": "Find Expansions", "action": "expand"},
                {"label": "Approve & Launch", "action": "launch"},
                {"label": "Mine Search Terms", "action": "mine_search_terms"},
            ],
        }

    async def _trigger_full_audit(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Run campaign audit (+ LP audit if applicable) then auto-suggest expansions."""
        reply = ""

        # Campaign audit
        audit_data = await self._run_campaign_audit(state)
        campaign_audit = audit_data.get("campaign_audit", {})
        reply += "**Campaign Quality Audit:**\n\n"
        reply += self._format_audit_summary(campaign_audit)

        # LP audit if URL exists
        if state.get("landing_page_url"):
            reply += "\n\n---\n\n**Landing Page Audit:**\n\n"
            lp_audit = await self._run_lp_audit(state)
            reply += f"Score: {lp_audit.get('overall_score', 0)}/100 ({lp_audit.get('grade', '?')})\n"

        # Auto-trigger expansion
        reply += "\n\n---\n\n**Scanning for expansions...**\n\n"
        expansion_data = await self._run_expansion(profile, state)
        expansions = expansion_data.get("expansions", [])
        reply += self._format_expansion_summary(expansion_data)

        if expansions:
            reply += "\n\n**How many expansion campaigns would you like?**"
            state["phase"] = PHASE_EXPANSION
            return {
                "reply": reply,
                "phase": PHASE_EXPANSION,
                "campaign_audit": campaign_audit, "expansions": expansions,
                "session_state": state,
                "quick_actions": [
                    {"label": "Generate Top 5 Makes", "action": "expand_5"},
                    {"label": "Generate Top 10 Makes", "action": "expand_10"},
                    {"label": "Generate Top 25 Makes", "action": "expand_25"},
                    {"label": "Skip Expansions", "action": "skip_expansion"},
                ],
            }

        state["phase"] = PHASE_AUDIT_DONE
        return self._reply(
            reply + "\n\n**Campaign is ready!**",
            PHASE_AUDIT_DONE, state,
            campaign_audit=campaign_audit,
            quick_actions=[
                {"label": "Approve & Launch", "action": "launch"},
                {"label": "Mine Search Terms", "action": "mine_search_terms"},
                {"label": "Build Another Campaign", "action": "new_campaign"},
            ],
        )

    async def _trigger_expansion(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Run expansion scoring and present results."""
        result = await self._run_expansion(profile, state)
        expansions = result.get("expansions", [])
        state["phase"] = PHASE_EXPANSION

        if not expansions:
            return await self._continuous_recommendation(profile, state)

        reply = self._format_expansion_summary(result)
        reply += "\n\n**How many would you like to generate?**"

        return {
            "reply": reply,
            "phase": PHASE_EXPANSION,
            "expansions": expansions,
            "session_state": state,
            "quick_actions": [
                {"label": "Generate Top 5 Makes", "action": "expand_5"},
                {"label": "Generate Top 10 Makes", "action": "expand_10"},
                {"label": "Generate Top 25 Makes", "action": "expand_25"},
                {"label": "Generate All + Landing Pages", "action": "expand_all"},
                {"label": "Skip", "action": "skip_expansion"},
            ],
        }

    async def _trigger_search_term_mining(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Run search term mining and surface insights."""
        result = await self._run_search_term_mining(state)

        if result.get("status") == "no_account":
            return self._reply(
                "No Google Ads account connected. Connect your account in **Settings** to enable search term mining.",
                state.get("phase", PHASE_IDLE), state,
                quick_actions=[
                    {"label": "Build Another Campaign", "action": "new_campaign"},
                    {"label": "What Should I Do Next?", "action": "what_next"},
                ],
            )

        if result.get("status") == "no_data":
            return self._reply(
                f"**Search Term Mining:** {result.get('message', 'No data yet.')}\n\n"
                "Your campaigns need at least 7 days of data before mining insights are available. "
                "I'll automatically analyze them once there's enough data.",
                state.get("phase", PHASE_IDLE), state,
                quick_actions=[
                    {"label": "Build Another Campaign", "action": "new_campaign"},
                    {"label": "What Should I Do Next?", "action": "what_next"},
                ],
            )

        # Format mining results
        add_kw = result.get("add_as_keyword", [])
        add_neg = result.get("add_as_negative", [])
        themes = result.get("new_ad_group_themes", [])
        wasted = result.get("wasted_spend", 0)
        total = result.get("total_spend_analyzed", 0)

        reply = f"**Search Term Mining Report**\n\n"
        reply += f"Analyzed **{result.get('analyzed_terms', 0)}** search terms over the last 30 days.\n\n"
        reply += f"{result.get('summary', '')}\n\n"

        if wasted > 0 and total > 0:
            pct = round(wasted / total * 100)
            reply += f"💰 **Wasted Spend:** ${wasted:,.2f} ({pct}% of ${total:,.2f} total)\n\n"

        if add_kw:
            reply += f"**Add as Keywords ({len(add_kw)}):**\n"
            for k in add_kw[:5]:
                reply += f"- `{k['search_term']}` — {k.get('reason', '')}\n"
            if len(add_kw) > 5:
                reply += f"- _...and {len(add_kw) - 5} more_\n"

        if add_neg:
            reply += f"\n**Add as Negatives ({len(add_neg)}):**\n"
            for n in add_neg[:5]:
                reply += f"- `{n['search_term']}` — ${n.get('cost_wasted', 0):.2f} wasted\n"
            if len(add_neg) > 5:
                reply += f"- _...and {len(add_neg) - 5} more_\n"

        if themes:
            reply += f"\n**New Ad Group Themes ({len(themes)}):**\n"
            for t in themes[:3]:
                reply += f"- **{t.get('theme', '')}** — {t.get('reason', '')}\n"

        state["phase"] = PHASE_OPTIMIZATION
        return self._reply(
            reply, PHASE_OPTIMIZATION, state,
            search_mining=result,
            quick_actions=[
                {"label": "Build Another Campaign", "action": "new_campaign"},
                {"label": "Find More Expansions", "action": "expand"},
                {"label": "What Should I Do Next?", "action": "what_next"},
            ],
        )

    # ── CONTINUOUS RECOMMENDATION ENGINE ──────────────────────────────

    async def _continuous_recommendation(self, profile: Optional[Dict], state: Dict) -> Dict:
        """AI continuously recommends what to build, improve, or expand next."""
        recommendations = []

        # Check what we have and haven't done
        has_campaign = bool(state.get("campaign_draft"))
        has_lp = bool(state.get("landing_page"))
        has_audit = bool(state.get("campaign_audit"))
        has_expansions = bool(state.get("expansions"))
        has_mining = bool(state.get("search_mining"))
        audit_score = state.get("campaign_audit", {}).get("overall_score", 100)

        if has_campaign and not has_lp:
            recommendations.append("**Generate a landing page** — campaigns with matched landing pages convert 2-3x better")
        if has_campaign and not has_audit:
            recommendations.append("**Run a quality audit** — catch issues before spending money")
        if has_campaign and not has_expansions:
            recommendations.append("**Find expansion opportunities** — discover related makes and services to target")
        if has_audit and audit_score < 70:
            recommendations.append(f"**Fix audit issues** — your campaign scored {audit_score}/100, regenerating could improve it")
        if has_campaign and not has_mining:
            recommendations.append("**Mine search terms** — find hidden opportunities and eliminate wasted spend")
        if has_expansions and not state.get("bulk_launched"):
            exp_count = len(state.get("expansions", []))
            recommendations.append(f"**Bulk generate {exp_count} expansion campaigns** — grow your coverage fast")

        # Always recommend
        recommendations.append("**Build another campaign** — target a new service or audience")

        reply = "**What Should You Do Next?**\n\n"
        reply += "Based on your current progress, here are my top recommendations:\n\n"
        for i, rec in enumerate(recommendations[:5], 1):
            reply += f"{i}. {rec}\n"

        reply += "\n**Pick an action or describe what you'd like to do:**"

        actions = []
        if has_campaign and not has_lp:
            actions.append({"label": "Generate Landing Page", "action": "generate_lp"})
        if has_campaign and not has_expansions:
            actions.append({"label": "Find Expansions", "action": "expand"})
        if not has_mining:
            actions.append({"label": "Mine Search Terms", "action": "mine_search_terms"})
        actions.append({"label": "Build New Campaign", "action": "new_campaign"})

        state["phase"] = PHASE_IDLE
        return self._reply(reply, PHASE_IDLE, state, quick_actions=actions)

    # ── BULK GENERATION ───────────────────────────────────────────────

    def _launch_bulk(self, selected_expansions: List[Dict], state: Dict) -> Dict:
        """Launch bulk generation for selected expansions."""
        variants = [e.get("service_name", "") for e in selected_expansions if e.get("service_name")]
        if not variants:
            return self._reply(
                "No valid expansions to generate. Try a different approach.",
                state.get("phase", PHASE_IDLE), state,
            )

        state["bulk_launched"] = True
        state["bulk_variants"] = variants
        state["phase"] = PHASE_BULK_LAUNCHED

        reply = f"**Launching {len(variants)} campaigns!** Running in background.\n\n"
        for v in variants:
            reply += f"- {v}\n"
        reply += (
            f"\nEach campaign includes keywords, ads, and extensions. "
            f"I'll track progress and notify you when done.\n\n"
            f"**While those generate, here's what I recommend next:**\n"
            f"- Mine search terms from existing campaigns to optimize spend\n"
            f"- Build landing pages for high-priority services\n"
            f"- Review and launch your primary campaign"
        )

        return {
            "reply": reply,
            "phase": PHASE_BULK_LAUNCHED,
            "session_state": state,
            "bulk_generate": {
                "service_variants": variants,
                "base_prompt": state.get("intent", {}).get("original_prompt", ""),
            },
            "quick_actions": [
                {"label": "Mine Search Terms", "action": "mine_search_terms"},
                {"label": "Generate Landing Pages", "action": "generate_lp"},
                {"label": "Build Another Campaign", "action": "new_campaign"},
                {"label": "What Should I Do Next?", "action": "what_next"},
            ],
        }

    # ── FORMATTING HELPERS ────────────────────────────────────────────

    def _format_audit_summary(self, audit: Dict) -> str:
        """Format campaign audit into readable summary."""
        score = audit.get("overall_score", 0)
        grade = audit.get("grade", "?")
        issues = audit.get("issues", [])
        strengths = audit.get("strengths", [])

        reply = f"**Score: {score}/100 ({grade})**\n\n"

        if strengths:
            reply += "**Strengths:** "
            reply += " • ".join(strengths[:3]) + "\n\n"

        if issues:
            critical = [i for i in issues if i.get("severity") == "critical"]
            warnings = [i for i in issues if i.get("severity") == "warning"]
            if critical:
                reply += f"**Critical ({len(critical)}):** "
                reply += " • ".join([f"{i['title']}" for i in critical[:3]]) + "\n"
            if warnings:
                reply += f"**Warnings ({len(warnings)}):** "
                reply += " • ".join([f"{i['title']}" for i in warnings[:3]]) + "\n"

        if audit.get("summary"):
            reply += f"\n{audit['summary']}"

        return reply

    def _format_expansion_summary(self, result: Dict) -> str:
        """Format expansion results into readable summary."""
        expansions = result.get("expansions", [])
        if not expansions:
            return "No expansion opportunities found at this time."

        make_exps = result.get("make_expansions", [])
        svc_exps = result.get("service_expansions", [])

        reply = f"**{len(expansions)} Expansion Opportunities Found!**\n\n"

        if make_exps:
            reply += f"**Make/Brand ({len(make_exps)}):**\n"
            for e in make_exps[:8]:
                reply += f"- **{e['service_name']}** — {e.get('score', 0)}/100\n"

        if svc_exps:
            reply += f"\n**Related Services ({len(svc_exps)}):**\n"
            for e in svc_exps[:5]:
                reply += f"- **{e['service_name']}** — {e.get('score', 0)}/100\n"

        if result.get("summary"):
            reply += f"\n{result['summary']}"

        return reply

    def _post_campaign_actions(self) -> List[Dict]:
        """Standard quick actions for post-campaign state."""
        return [
            {"label": "Generate Landing Page", "action": "generate_lp"},
            {"label": "Audit Campaign", "action": "audit_campaign"},
            {"label": "Find Expansions", "action": "expand"},
            {"label": "Mine Search Terms", "action": "mine_search_terms"},
            {"label": "Approve & Launch", "action": "launch"},
        ]

    def _reply(self, reply: str, phase: str, state: Dict, **extra) -> Dict:
        """Build standard reply dict."""
        state["phase"] = phase
        result = {
            "reply": reply,
            "phase": phase,
            "session_state": state,
            "quick_actions": extra.pop("quick_actions", []),
        }
        result.update(extra)
        return result

    # ── AI HELPERS ─────────────────────────────────────────────────────

    async def _parse_campaign_intent(self, message: str, profile: Optional[Dict]) -> Dict:
        """Use AI to extract structured intent from user's campaign description.

        Enhanced with self-audit quality checks: the AI validates its own extraction
        for completeness, flags gaps, and enriches with competitive intelligence.
        Handles long messages (e.g. pasted landing page content) by truncating
        to a reasonable size for the AI while preserving the full original prompt.
        """
        if not self.client:
            return {"service": message, "original_prompt": message}

        # Truncate very long messages (users may paste entire landing pages)
        truncated = message[:3000] if len(message) > 3000 else message
        was_truncated = len(message) > 3000

        profile_ctx = ""
        if profile:
            profile_ctx = f"""
BUSINESS PROFILE:
- Name: {profile.get('business_name', '')}
- Industry: {profile.get('industry', '')}
- Services: {json.dumps(profile.get('services', [])[:10])}
- Locations: {json.dumps(profile.get('locations', [])[:5])}
- USPs: {json.dumps(profile.get('usps', [])[:5])}
- Offers: {json.dumps(profile.get('offers', [])[:3])}
- Conversion goal: {profile.get('conversion_goal', 'calls')}
- Website: {profile.get('website', '')}
- Phone: {profile.get('phone', '')}"""

        system = """You are a senior Google Ads strategist with 15+ years managing $100M+ in
local service ad spend. You specialize in high-intent local campaigns (locksmith,
HVAC, plumbing, legal, auto repair, roofing, etc.).

Your job is to DEEPLY parse a business owner's campaign request into precise,
actionable campaign intelligence. You must:

1. EXTRACT — Pull every detail from the user's message: service, brand, location,
   urgency signals, competitive differentiators, pricing clues, audience signals.
2. ENRICH — Add industry knowledge the user didn't explicitly say but is critical
   for campaign success (seasonal factors, typical CPCs, competitor landscape,
   common search patterns for this service).
3. SELF-AUDIT — After extraction, check your own work:
   - Did I miss any services implied but not stated?
   - Are my keyword suggestions specific enough (long-tail > generic)?
   - Are expansion opportunities realistic for this business?
   - Did I correctly gauge urgency from context clues?
   - Are my selling points actually differentiating or just generic?
4. RECOMMEND FUNNEL — Based on the service type, urgency, ticket price, and
   customer journey for this specific industry, recommend the optimal conversion
   funnel with detailed reasoning.

Respond ONLY with valid JSON."""

        truncation_note = "\n\n(Content was truncated — extract what you can from above)" if was_truncated else ""

        prompt = f"""Parse this campaign request with DEEP analysis:

{truncated}
{truncation_note}
{profile_ctx}

Return JSON with ALL of these fields:
{{
  "service": "core service name (be specific, e.g. 'Jaguar BCM repair' not just 'car repair')",
  "service_category": "broader category (e.g. 'automotive locksmith', 'emergency plumbing')",
  "brand": "brand/make if mentioned, or null",
  "industry": "detected industry",
  "location": "location/area",
  "service_area_radius": "estimated service radius if mentioned (e.g. '25 miles')",
  "goal": "phone calls" | "form leads" | "bookings" | "store visits",
  "urgency": "emergency" | "urgent" | "standard" | "research",
  "intent_level": "high" | "medium" | "low",
  "estimated_ticket_value": "low (<$100)" | "medium ($100-500)" | "high ($500-2000)" | "premium ($2000+)",
  "customer_journey": "immediate (call now)" | "short (same day research)" | "considered (multi-day comparison)",
  "suggested_keywords": ["15-25 specific long-tail keywords for this exact service"],
  "negative_keywords": ["5-10 negative keywords to exclude waste"],
  "related_services": ["closely related services this business likely offers"],
  "expansion_potential": ["specific makes/brands/variations for expansion campaigns"],
  "landing_page_needed": true | false,
  "landing_page_reference_url": "URL if user pasted LP content or mentioned a URL, else null",
  "key_selling_points": ["extracted USPs — must be SPECIFIC differentiators, not generic"],
  "missing_info": ["information I'd want to ask the business owner for better campaigns"],
  "competitive_insights": "brief note on typical competitor landscape for this service",
  "seasonal_factors": "any time-of-year relevance, or null",
  "recommended_funnel": {{
    "type": "call_only" | "lp_call" | "lp_form" | "lp_booking" | "direct_call",
    "type_label": "human-readable label",
    "reason": "detailed explanation of WHY this funnel is best for THIS specific service, customer journey, and urgency level — reference real conversion data patterns",
    "confidence": "high" | "medium" | "low",
    "alternative": "second-best funnel option and when it would be better"
  }},
  "ad_angle": "the primary emotional/logical angle for ad copy (e.g. 'trust + expertise' or 'speed + availability')",
  "quality_score": {{
    "extraction_completeness": 1-10,
    "keyword_specificity": 1-10,
    "expansion_realism": 1-10,
    "overall": 1-10,
    "gaps_found": ["any gaps in the extraction that could hurt campaign quality"]
  }}
}}"""

        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=2500,
                timeout=45,
            )
            content = resp.choices[0].message.content
            if content:
                result = json.loads(content)
                result["original_prompt"] = message
                result["_ai_parsed"] = True
                return result
        except Exception as e:
            logger.error("Intent parsing failed", error=str(e), msg_len=len(message))

        return {"service": message[:200], "original_prompt": message}

    async def _smart_route(
        self, message: str, history: List[Dict], profile: Optional[Dict], state: Dict
    ) -> Dict:
        """Fallback: let AI decide what the user wants based on context."""
        if not self.client:
            return self._reply(
                "I'm not sure what you'd like to do. Try describing a campaign idea, "
                "or ask me to audit, expand, mine search terms, or build a landing page.",
                state.get("phase", PHASE_IDLE), state,
                quick_actions=[
                    {"label": "Build New Campaign", "action": "new_campaign"},
                    {"label": "Audit My Campaigns", "action": "audit_all"},
                    {"label": "Mine Search Terms", "action": "mine_search_terms"},
                    {"label": "What Should I Do Next?", "action": "what_next"},
                ],
            )

        system = """You are an AI marketing operator for a Google Ads management platform.
Based on the user's message and conversation context, provide a helpful response.
You can: build campaigns, generate landing pages, audit work, suggest expansions,
mine search terms, bulk-generate campaigns, and continuously improve marketing.
Be proactive — always suggest what to do next.
Respond with valid JSON: {"reply": "your response in markdown", "suggested_action": "action_key or null"}"""

        ctx = f"Current phase: {state.get('phase', 'idle')}\n"
        if state.get("intent"):
            ctx += f"Active intent: {json.dumps(state['intent'], default=str)[:300]}\n"
        if state.get("campaign_audit"):
            ctx += f"Audit score: {state['campaign_audit'].get('overall_score', '?')}/100\n"
        if state.get("expansions"):
            ctx += f"Expansion opportunities: {len(state['expansions'])}\n"

        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Context:\n{ctx}\n\nUser says: {message}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.6,
                max_tokens=1000,
            )
            content = resp.choices[0].message.content
            if content:
                data = json.loads(content)
                return self._reply(
                    data.get("reply", "I can help with that. What would you like to do?"),
                    state.get("phase", PHASE_IDLE), state,
                    quick_actions=[
                        {"label": "Build Campaign", "action": "new_campaign"},
                        {"label": "Generate Landing Page", "action": "generate_lp"},
                        {"label": "Audit Campaigns", "action": "audit_all"},
                        {"label": "Mine Search Terms", "action": "mine_search_terms"},
                    ],
                )
        except Exception as e:
            logger.error("Smart route failed", error=str(e))

        return self._reply(
            "How can I help? I can build campaigns, generate landing pages, "
            "audit your ads, mine search terms, or find expansion opportunities.",
            PHASE_IDLE, state,
            quick_actions=[
                {"label": "Build Campaign", "action": "new_campaign"},
                {"label": "What Should I Do Next?", "action": "what_next"},
            ],
        )
