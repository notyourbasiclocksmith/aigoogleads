"""
Strategist Orchestrator — The AI Marketing Operator brain.

Manages the multi-step campaign strategist chat flow:
  1. Parse intent from user prompt
  2. Ask about landing page
  3. Build campaign
  4. Build landing page (if requested)
  5. Audit campaign + landing page
  6. Recommend expansions
  7. Continuously suggest what's missing

This is the central coordinator that calls all other services/agents.
"""
import json
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.business_profile import BusinessProfile
from app.models.campaign import Campaign

logger = structlog.get_logger()


# Chat phases the orchestrator tracks
PHASE_INTENT = "intent_parsed"
PHASE_LP_DECISION = "landing_page_decision"
PHASE_GENERATING = "generating_campaign"
PHASE_CAMPAIGN_READY = "campaign_ready"
PHASE_LP_GENERATING = "generating_landing_page"
PHASE_LP_READY = "landing_page_ready"
PHASE_AUDITING = "auditing"
PHASE_AUDIT_DONE = "audit_complete"
PHASE_EXPANSION = "expansion_suggestions"
PHASE_IDLE = "idle"


class StrategistOrchestrator:
    """
    Stateless orchestrator — receives full conversation + phase state,
    determines next action, executes it, returns updated state + AI reply.
    """

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        session_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Main entry point. Processes user message, determines phase,
        executes appropriate agent, returns response + updated state.
        """
        phase = session_state.get("phase", "")
        intent = session_state.get("intent", {})

        # Load business context
        profile = await self._load_profile()

        # Determine what to do based on phase + message
        if not phase or phase == PHASE_IDLE:
            # New conversation or fresh start — parse intent
            return await self._handle_intent_parsing(user_message, profile, session_state)

        elif phase == PHASE_INTENT:
            # We've parsed intent, waiting for LP decision or user wants to adjust
            return await self._handle_post_intent(user_message, profile, session_state)

        elif phase == PHASE_LP_DECISION:
            # User responded to LP question
            return await self._handle_lp_decision(user_message, profile, session_state)

        elif phase == PHASE_CAMPAIGN_READY:
            # Campaign is built, user can audit, generate LP, expand, or adjust
            return await self._handle_post_campaign(user_message, profile, session_state)

        elif phase == PHASE_LP_READY:
            # Landing page is built
            return await self._handle_post_lp(user_message, profile, session_state)

        elif phase == PHASE_AUDIT_DONE:
            # Audits complete, expansion time
            return await self._handle_post_audit(user_message, profile, session_state)

        elif phase == PHASE_EXPANSION:
            # Expansion suggestions shown, user choosing
            return await self._handle_expansion_choice(user_message, profile, session_state)

        else:
            # Catch-all: use the smart router
            return await self._smart_route(user_message, conversation_history, profile, session_state)

    async def _load_profile(self) -> Optional[Dict]:
        result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        p = result.scalar_one_or_none()
        if not p:
            return None
        services = p.services_json if isinstance(p.services_json, list) else []
        svc_names = [s if isinstance(s, str) else s.get("name", "") for s in services]
        locations = p.locations_json if isinstance(p.locations_json, list) else []
        loc_names = [l if isinstance(l, str) else l.get("name", "") for l in locations]
        usps = p.usp_json if isinstance(p.usp_json, list) else []
        usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in usps]
        offers = p.offers_json if isinstance(p.offers_json, list) else []
        offer_texts = [o if isinstance(o, str) else o.get("text", "") for o in offers]
        return {
            "business_name": p.business_name or "",
            "industry": p.industry_classification or "",
            "phone": p.phone or "",
            "website": p.website_url or "",
            "services": svc_names,
            "locations": loc_names,
            "usps": usp_texts,
            "offers": offer_texts,
            "conversion_goal": p.primary_conversion_goal or "calls",
        }

    # ── PHASE HANDLERS ────────────────────────────────────────────────

    async def _handle_intent_parsing(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Parse user's campaign idea into structured intent."""
        intent = await self._parse_campaign_intent(message, profile)

        reply_parts = [
            f"**Got it!** Here's what I understand:\n",
            f"- **Service:** {intent.get('service', 'N/A')}",
        ]
        if intent.get("brand"):
            reply_parts.append(f"- **Brand/Make:** {intent['brand']}")
        reply_parts.extend([
            f"- **Location:** {intent.get('location', 'N/A')}",
            f"- **Industry:** {intent.get('industry', 'N/A')}",
            f"- **Goal:** {intent.get('goal', 'phone calls')}",
            f"- **Urgency:** {intent.get('urgency', 'standard')}",
        ])

        if intent.get("related_services"):
            reply_parts.append(f"\n**Related services detected:** {', '.join(intent['related_services'][:5])}")
        if intent.get("expansion_potential"):
            reply_parts.append(f"**Expansion potential:** {', '.join(intent['expansion_potential'][:5])}")

        reply_parts.append(
            "\n---\n**Before I build your campaign, do you have a landing page for this service?**"
        )

        return {
            "reply": "\n".join(reply_parts),
            "phase": PHASE_INTENT,
            "intent": intent,
            "quick_actions": [
                {"label": "Use Existing Landing Page", "action": "lp_existing"},
                {"label": "Create AI Landing Page", "action": "lp_create"},
                {"label": "Skip Landing Page", "action": "lp_skip"},
                {"label": "Adjust Campaign Details", "action": "adjust"},
            ],
            "session_state": {**state, "phase": PHASE_INTENT, "intent": intent},
        }

    async def _handle_post_intent(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle response after intent parsing — LP decision or adjustment."""
        msg_lower = message.lower().strip()
        intent = state.get("intent", {})

        # Check if user wants to adjust
        if any(w in msg_lower for w in ["adjust", "change", "modify", "edit", "wrong", "no"]):
            return await self._handle_intent_parsing(message, profile, state)

        # Route to LP decision
        if any(w in msg_lower for w in ["existing", "have a page", "url", "my page"]):
            return {
                "reply": "Please paste the URL of your existing landing page and I'll audit it for campaign alignment.",
                "phase": PHASE_LP_DECISION,
                "session_state": {**state, "phase": PHASE_LP_DECISION, "lp_choice": "existing"},
                "quick_actions": [],
            }
        elif any(w in msg_lower for w in ["create", "generate", "build", "new page", "ai page", "lp_create"]):
            state["lp_choice"] = "create"
            return await self._generate_campaign_and_lp(profile, state)
        else:
            # Default: skip LP, just build campaign
            state["lp_choice"] = "skip"
            return await self._generate_campaign_only(profile, state)

    async def _handle_lp_decision(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle LP URL input or other LP decisions."""
        lp_choice = state.get("lp_choice", "skip")

        if lp_choice == "existing" and message.strip().startswith("http"):
            # User provided URL — audit it, then build campaign
            state["landing_page_url"] = message.strip()
            return await self._generate_campaign_with_audit(message.strip(), profile, state)

        # Fallback: build campaign
        return await self._generate_campaign_only(profile, state)

    async def _handle_post_campaign(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle actions after campaign is built."""
        msg_lower = message.lower().strip()

        if any(w in msg_lower for w in ["landing page", "create page", "generate page", "build page", "lp"]):
            return await self._trigger_landing_page_gen(profile, state)
        elif any(w in msg_lower for w in ["audit", "check", "review", "score"]):
            return await self._trigger_campaign_audit(state)
        elif any(w in msg_lower for w in ["expand", "similar", "more makes", "related", "grow"]):
            return await self._trigger_expansion(profile, state)
        elif any(w in msg_lower for w in ["launch", "approve", "go live"]):
            return {
                "reply": "Campaign is ready to launch! Click **Approve & Launch** in the campaign preview above to push it to Google Ads.",
                "phase": PHASE_CAMPAIGN_READY,
                "session_state": state,
                "quick_actions": [
                    {"label": "Generate Landing Page", "action": "generate_lp"},
                    {"label": "Audit Campaign", "action": "audit_campaign"},
                    {"label": "Expand to Similar Makes", "action": "expand_makes"},
                    {"label": "Expand to Related Services", "action": "expand_services"},
                ],
            }
        else:
            return await self._smart_route(message, [], profile, state)

    async def _handle_post_lp(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle actions after landing page is built."""
        msg_lower = message.lower().strip()

        if any(w in msg_lower for w in ["audit", "score", "check"]):
            return await self._trigger_campaign_audit(state)
        elif any(w in msg_lower for w in ["expand", "more", "similar"]):
            return await self._trigger_expansion(profile, state)
        else:
            return await self._trigger_campaign_audit(state)

    async def _handle_post_audit(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle actions after audits are complete."""
        return await self._trigger_expansion(profile, state)

    async def _handle_expansion_choice(
        self, message: str, profile: Optional[Dict], state: Dict
    ) -> Dict[str, Any]:
        """Handle expansion selection (top 5, top 10, etc.)."""
        msg_lower = message.lower().strip()
        expansions = state.get("expansions", [])

        count = 5  # default
        if "10" in msg_lower or "ten" in msg_lower:
            count = 10
        elif "25" in msg_lower or "twenty" in msg_lower:
            count = 25
        elif "50" in msg_lower or "fifty" in msg_lower:
            count = 50
        elif "all" in msg_lower:
            count = len(expansions)
        elif "skip" in msg_lower or "no" in msg_lower:
            return {
                "reply": "No problem! Your campaign is ready. Is there anything else you'd like me to help with?\n\nI can:\n- Build another campaign\n- Audit existing campaigns\n- Generate landing pages\n- Find more growth opportunities",
                "phase": PHASE_IDLE,
                "session_state": {**state, "phase": PHASE_IDLE},
                "quick_actions": [
                    {"label": "Build Another Campaign", "action": "new_campaign"},
                    {"label": "Audit My Campaigns", "action": "audit_all"},
                ],
            }

        selected = expansions[:count]
        variants = [e.get("service_name", "") for e in selected]

        return {
            "reply": f"**Generating {len(variants)} campaigns!** This will run in the background.\n\n"
                     + "\n".join([f"- {v}" for v in variants])
                     + f"\n\nEach campaign will include keywords, ads, and extensions. I'll notify you when they're ready.",
            "phase": PHASE_IDLE,
            "session_state": {**state, "phase": PHASE_IDLE},
            "bulk_generate": {
                "service_variants": variants,
                "base_prompt": state.get("intent", {}).get("original_prompt", ""),
            },
            "quick_actions": [],
        }

    # ── ACTION TRIGGERS ────────────────────────────────────────────────

    async def _generate_campaign_only(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Build campaign without landing page."""
        intent = state.get("intent", {})
        from app.services.campaign_generator import CampaignGeneratorService
        from sqlalchemy import select as sa_select
        from app.models.business_profile import BusinessProfile as BPModel

        prompt = intent.get("original_prompt", intent.get("service", ""))
        generator = CampaignGeneratorService(self.db, self.tenant_id)

        # Load actual BusinessProfile ORM object for the generator
        bp_result = await self.db.execute(
            sa_select(BPModel).where(BPModel.tenant_id == self.tenant_id)
        )
        bp_obj = bp_result.scalar_one_or_none()

        if bp_obj:
            draft = await generator.generate_from_prompt(prompt, bp_obj)
        else:
            # Fallback: create a minimal dummy profile dict
            draft = {"campaign": {"name": intent.get("service", "Campaign")}, "ad_groups": [], "error": "No business profile found. Please complete onboarding first."}

        state["campaign_draft"] = draft
        state["phase"] = PHASE_CAMPAIGN_READY

        ag_count = len(draft.get("ad_groups", []))
        kw_count = sum(len(ag.get("keywords", [])) for ag in draft.get("ad_groups", []))

        reply = (
            f"**Campaign Built!** Here's your draft:\n\n"
            f"- **Campaign:** {draft.get('campaign', {}).get('name', 'N/A')}\n"
            f"- **Ad Groups:** {ag_count}\n"
            f"- **Keywords:** {kw_count}\n"
            f"- **Ads:** {sum(len(ag.get('ads', [])) for ag in draft.get('ad_groups', []))}\n\n"
            f"**What's next?** I can:"
        )

        return {
            "reply": reply,
            "phase": PHASE_CAMPAIGN_READY,
            "campaign_draft": draft,
            "session_state": state,
            "quick_actions": [
                {"label": "Generate Landing Page", "action": "generate_lp"},
                {"label": "Audit Campaign Quality", "action": "audit_campaign"},
                {"label": "Expand to Similar Makes", "action": "expand_makes"},
                {"label": "Expand to Related Services", "action": "expand_services"},
                {"label": "Create 10 More Campaigns", "action": "bulk_10"},
                {"label": "Approve & Launch", "action": "launch"},
            ],
        }

    async def _generate_campaign_and_lp(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Build campaign + landing page together."""
        result = await self._generate_campaign_only(profile, state)
        lp_result = await self._trigger_landing_page_gen(profile, state)

        result["reply"] += "\n\n---\n\n" + lp_result.get("reply", "")
        result["landing_page"] = lp_result.get("landing_page")
        result["phase"] = PHASE_LP_READY
        state["phase"] = PHASE_LP_READY
        result["session_state"] = state
        result["quick_actions"] = [
            {"label": "Audit Everything", "action": "audit_all"},
            {"label": "Expand to Similar Makes", "action": "expand_makes"},
            {"label": "Create 10 More Campaigns", "action": "bulk_10"},
            {"label": "Approve & Launch", "action": "launch"},
        ]
        return result

    async def _generate_campaign_with_audit(self, url: str, profile: Optional[Dict], state: Dict) -> Dict:
        """Build campaign + audit existing landing page."""
        result = await self._generate_campaign_only(profile, state)

        # Audit the existing page
        from app.services.landing_page_auditor import LandingPageAuditor
        intent = state.get("intent", {})
        auditor = LandingPageAuditor(self.db, self.tenant_id)
        audit = await auditor.audit_url(
            url=url,
            campaign_keywords=intent.get("suggested_keywords", []),
            service=intent.get("service", ""),
            location=intent.get("location", ""),
        )

        state["lp_audit"] = audit
        result["lp_audit"] = audit

        score = audit.get("overall_score", 0)
        grade = audit.get("grade", "?")
        result["reply"] += (
            f"\n\n---\n\n**Landing Page Audit: {score}/100 ({grade})**\n\n"
        )
        for issue in audit.get("top_issues", [])[:3]:
            result["reply"] += f"- {issue}\n"

        if audit.get("top_recommendations"):
            result["reply"] += f"\n**Recommendations:**\n"
            for rec in audit["top_recommendations"][:3]:
                result["reply"] += f"- {rec}\n"

        if score < 70:
            result["reply"] += "\n**Your page scored below 70.** I recommend creating an AI-optimized landing page instead."
            result["quick_actions"].insert(0, {"label": "Create AI Landing Page", "action": "generate_lp"})

        return result

    async def _trigger_landing_page_gen(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Generate landing page for the current campaign."""
        from app.services.landing_page_generator import LandingPageGenerator

        intent = state.get("intent", {})
        draft = state.get("campaign_draft", {})

        # Extract keywords and headlines from draft
        keywords = []
        headlines = []
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
        )

        state["landing_page"] = lp
        state["phase"] = PHASE_LP_READY

        if lp.get("error"):
            return {
                "reply": f"Landing page generation failed: {lp['error']}",
                "phase": PHASE_CAMPAIGN_READY,
                "session_state": state,
                "quick_actions": [],
            }

        variants = lp.get("variants", [])
        reply = (
            f"**Landing Page Generated!** 3 variants ready for preview:\n\n"
        )
        for v in variants:
            reply += f"- **Variant {v['key']}** — {v['name']}\n"

        reply += f"\nPage slug: `{lp.get('slug', '')}`"

        return {
            "reply": reply,
            "phase": PHASE_LP_READY,
            "landing_page": lp,
            "session_state": state,
            "quick_actions": [
                {"label": "Audit Everything", "action": "audit_all"},
                {"label": "Expand to Similar Makes", "action": "expand_makes"},
                {"label": "Approve & Launch", "action": "launch"},
            ],
        }

    async def _trigger_campaign_audit(self, state: Dict) -> Dict:
        """Run AI audit on the campaign draft."""
        from app.services.campaign_auditor import CampaignAuditor

        draft = state.get("campaign_draft", {})
        auditor = CampaignAuditor(self.db, self.tenant_id)
        audit = await auditor.audit_draft(draft)

        state["campaign_audit"] = audit
        state["phase"] = PHASE_AUDIT_DONE

        score = audit.get("overall_score", 0)
        grade = audit.get("grade", "?")
        issues = audit.get("issues", [])
        strengths = audit.get("strengths", [])

        reply = f"**Campaign Audit: {score}/100 ({grade})**\n\n"

        if strengths:
            reply += "**Strengths:**\n"
            for s in strengths[:3]:
                reply += f"- {s}\n"

        if issues:
            critical = [i for i in issues if i.get("severity") == "critical"]
            warnings = [i for i in issues if i.get("severity") == "warning"]
            if critical:
                reply += f"\n**Critical Issues ({len(critical)}):**\n"
                for i in critical[:3]:
                    reply += f"- {i['title']}: {i.get('details', '')}\n"
            if warnings:
                reply += f"\n**Warnings ({len(warnings)}):**\n"
                for i in warnings[:3]:
                    reply += f"- {i['title']}\n"

        reply += f"\n{audit.get('summary', '')}"
        reply += "\n\n**Ready to find expansion opportunities?**"

        return {
            "reply": reply,
            "phase": PHASE_AUDIT_DONE,
            "campaign_audit": audit,
            "session_state": state,
            "quick_actions": [
                {"label": "Expand to Similar Makes", "action": "expand_makes"},
                {"label": "Expand to Related Services", "action": "expand_services"},
                {"label": "Fix Issues & Regenerate", "action": "regenerate"},
                {"label": "Approve As-Is", "action": "launch"},
            ],
        }

    async def _trigger_expansion(self, profile: Optional[Dict], state: Dict) -> Dict:
        """Run expansion scoring from the current campaign."""
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

        expansions = result.get("expansions", [])
        state["expansions"] = expansions
        state["phase"] = PHASE_EXPANSION

        if not expansions:
            return {
                "reply": "I couldn't identify expansion opportunities right now. Your campaign is ready to launch!",
                "phase": PHASE_IDLE,
                "session_state": {**state, "phase": PHASE_IDLE},
                "quick_actions": [{"label": "Approve & Launch", "action": "launch"}],
            }

        make_exps = result.get("make_expansions", [])
        svc_exps = result.get("service_expansions", [])

        reply = f"**Expansion Opportunities Found!** ({len(expansions)} total)\n\n"

        if make_exps:
            reply += f"**Make/Brand Expansions ({len(make_exps)}):**\n"
            for e in make_exps[:8]:
                reply += f"- **{e['service_name']}** — Score: {e.get('score', 0)}/100\n"

        if svc_exps:
            reply += f"\n**Service Expansions ({len(svc_exps)}):**\n"
            for e in svc_exps[:5]:
                reply += f"- **{e['service_name']}** — Score: {e.get('score', 0)}/100\n"

        if result.get("summary"):
            reply += f"\n{result['summary']}"

        reply += "\n\n**How many would you like to generate?**"

        return {
            "reply": reply,
            "phase": PHASE_EXPANSION,
            "expansions": expansions,
            "session_state": state,
            "quick_actions": [
                {"label": "Create Top 5", "action": "expand_5"},
                {"label": "Create Top 10", "action": "expand_10"},
                {"label": "Create Top 25", "action": "expand_25"},
                {"label": "Create All + Landing Pages", "action": "expand_all"},
                {"label": "Skip", "action": "skip_expansion"},
            ],
        }

    # ── AI HELPERS ─────────────────────────────────────────────────────

    async def _parse_campaign_intent(self, message: str, profile: Optional[Dict]) -> Dict:
        """Use AI to extract structured intent from user's campaign description."""
        if not self.client:
            return {"service": message, "original_prompt": message}

        profile_ctx = ""
        if profile:
            profile_ctx = f"""
BUSINESS PROFILE:
- Name: {profile.get('business_name', '')}
- Industry: {profile.get('industry', '')}
- Services: {json.dumps(profile.get('services', [])[:10])}
- Locations: {json.dumps(profile.get('locations', [])[:5])}"""

        system = """You are an expert Google Ads campaign strategist. Parse the user's campaign
description into structured data. Identify the core service, brand/make if any,
location, industry, urgency level, goal, and expansion potential.
Respond ONLY with valid JSON."""

        prompt = f"""Parse this campaign request:

"{message}"
{profile_ctx}

Return JSON:
{{
  "service": "core service name",
  "brand": "brand/make if mentioned, or null",
  "industry": "detected industry",
  "location": "location/area",
  "goal": "phone calls" | "form leads" | "bookings" | "store visits",
  "urgency": "emergency" | "urgent" | "standard" | "research",
  "intent_level": "high" | "medium" | "low",
  "suggested_keywords": ["keyword1", "keyword2", ...],
  "related_services": ["related service 1", "related service 2", ...],
  "expansion_potential": ["make/brand expansion 1", "make/brand expansion 2", ...],
  "landing_page_needed": true | false,
  "original_prompt": "{message}"
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
                max_tokens=1000,
            )
            content = resp.choices[0].message.content
            if content:
                result = json.loads(content)
                result["original_prompt"] = message
                return result
        except Exception as e:
            logger.error("Intent parsing failed", error=str(e))

        return {"service": message, "original_prompt": message}

    async def _smart_route(
        self, message: str, history: List[Dict], profile: Optional[Dict], state: Dict
    ) -> Dict:
        """Fallback: let AI decide what the user wants based on context."""
        if not self.client:
            return {
                "reply": "I'm not sure what you'd like to do. Try describing a campaign idea, or ask me to audit, expand, or build a landing page.",
                "phase": state.get("phase", PHASE_IDLE),
                "session_state": state,
                "quick_actions": [
                    {"label": "Build New Campaign", "action": "new_campaign"},
                    {"label": "Audit My Campaigns", "action": "audit_all"},
                ],
            }

        system = """You are an AI marketing operator for a Google Ads management platform.
Based on the user's message and conversation context, provide a helpful response.
You can build campaigns, generate landing pages, audit work, suggest expansions,
and continuously improve marketing. Be proactive — always suggest what to do next.
Respond with valid JSON: {"reply": "your response in markdown", "suggested_action": "action_key or null"}"""

        ctx = f"Current phase: {state.get('phase', 'idle')}\n"
        if state.get("intent"):
            ctx += f"Active intent: {json.dumps(state['intent'], default=str)[:300]}\n"

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
                return {
                    "reply": data.get("reply", "I can help with that. What would you like to do?"),
                    "phase": state.get("phase", PHASE_IDLE),
                    "session_state": state,
                    "quick_actions": [
                        {"label": "Build Campaign", "action": "new_campaign"},
                        {"label": "Generate Landing Page", "action": "generate_lp"},
                        {"label": "Audit Campaigns", "action": "audit_all"},
                        {"label": "Find Expansions", "action": "expand"},
                    ],
                }
        except Exception as e:
            logger.error("Smart route failed", error=str(e))

        return {
            "reply": "How can I help? I can build campaigns, generate landing pages, audit your ads, or find expansion opportunities.",
            "phase": PHASE_IDLE,
            "session_state": state,
            "quick_actions": [
                {"label": "Build Campaign", "action": "new_campaign"},
                {"label": "Generate Landing Page", "action": "generate_lp"},
            ],
        }
