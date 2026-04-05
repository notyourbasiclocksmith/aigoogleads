"""
Multi-Agent Campaign Creation Pipeline
======================================

6 specialized Claude agents collaborate to build expert-quality Google Ads campaigns.
Each agent focuses deeply on one aspect, receives rich context, and produces
validated output that feeds into the next stage.

Pipeline:
  1. Strategist Agent (sequential) — campaign architecture
  2. Keyword Research Agent  ─┐
  3. Targeting Agent          ├─ parallel
  4. Extensions Agent        ─┘
  5. Ad Copy Agent (sequential, needs keywords)
  6. QA Agent (sequential, reviews assembled spec)
"""

import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import anthropic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.operator import OperatorMessage
from app.models.business_profile import BusinessProfile

logger = structlog.get_logger()


class CampaignAgentPipeline:
    """Multi-agent Claude pipeline for expert-quality campaign creation."""

    def __init__(self, db: AsyncSession, tenant_id: str, customer_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL
        self.conversation_id: Optional[str] = None

    # ── ORCHESTRATOR ─────────────────────────────────────────────

    async def run(
        self,
        user_prompt: str,
        account_context: Dict[str, Any],
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Execute the full 6-agent pipeline. Returns deploy_full_campaign spec."""
        self.conversation_id = conversation_id
        logger.info("Campaign pipeline started", conversation_id=conversation_id)

        # Gather all context the agents will need
        context = await self._gather_context(account_context)

        # ── Agent 1: Strategist (everything depends on this) ──
        await self._emit_progress("Strategist", "running", "Analyzing your business, competitors, and existing campaigns to design the optimal campaign architecture...")
        strategy = await self._agent_strategist(context, user_prompt)
        if not strategy:
            await self._emit_progress("Strategist", "error", "Failed to generate strategy")
            return self._fallback_spec(user_prompt, context)
        await self._emit_progress("Strategist", "done",
            f"{strategy.get('campaign_type', 'SEARCH')} campaign \u2022 ${strategy.get('budget_daily', 50)}/day \u2022 {len(strategy.get('services', []))} ad groups")

        # ── Agents 2-4: Parallel (independent of each other) ──
        await self._emit_progress("Keyword Research", "running", f"Building tiered keyword strategy across {len(strategy.get('services', []))} services...")
        await self._emit_progress("Targeting", "running", "Configuring geo-targeting, device bids, and ad schedule...")
        await self._emit_progress("Extensions", "running", "Generating sitelinks, callouts, and structured snippets...")

        keywords, targeting, extensions = await asyncio.gather(
            self._agent_keyword_research(context, strategy),
            self._agent_targeting(context, strategy),
            self._agent_extensions(context, strategy),
        )

        kw_count = len(keywords.get("keywords", [])) if keywords else 0
        neg_count = len(keywords.get("negatives", [])) if keywords else 0
        await self._emit_progress("Keyword Research", "done", f"{kw_count} keywords \u2022 {neg_count} negatives \u2022 tiered by intent")
        await self._emit_progress("Targeting", "done",
            f"{targeting.get('geo', {}).get('radius_miles', 40)}-mile radius \u2022 Mobile +{targeting.get('device_bids', {}).get('mobile_bid_adj', 0)}%"
            if targeting else "Targeting configured")
        await self._emit_progress("Extensions", "done",
            f"{len(extensions.get('sitelinks', []))} sitelinks \u2022 {len(extensions.get('callouts', []))} callouts"
            if extensions else "Extensions generated")

        # ── Agent 5: Ad Copy (needs keywords for ad group alignment) ──
        await self._emit_progress("Ad Copy", "running", f"Writing 15 headlines + 4 descriptions per ad group with pinning strategy...")
        ad_copy = await self._agent_ad_copy(context, strategy, keywords or {})
        ag_count = len(ad_copy.get("ad_groups", [])) if ad_copy else 0
        await self._emit_progress("Ad Copy", "done", f"{ag_count} ad groups with full RSA copy")

        # ── Assemble the full spec ──
        spec = self._assemble_spec(
            strategy or {},
            keywords or {},
            ad_copy or {},
            targeting or {},
            extensions or {},
        )

        # ── Agent 6: QA Review ──
        await self._emit_progress("Quality Assurance", "running", "Auditing compliance, keyword-ad relevance, character limits, and campaign structure...")
        qa_result = await self._agent_qa(spec, context, user_prompt)
        if qa_result:
            score = qa_result.get("score", 0)
            spec = self._apply_qa_fixes(spec, qa_result)
            await self._emit_progress("Quality Assurance", "done",
                f"Score: {score}/100 \u2022 {len(qa_result.get('issues', []))} issues found \u2022 Auto-fixed")
        else:
            await self._emit_progress("Quality Assurance", "done", "Review complete")

        logger.info("Campaign pipeline complete",
            campaign_name=spec.get("campaign", {}).get("name"),
            ad_groups=len(spec.get("ad_groups", [])),
        )
        return spec

    # ── CONTEXT GATHERING ────────────────────────────────────────

    async def _gather_context(self, account_context: Dict) -> Dict[str, Any]:
        """Load business profile, competitor intel, and format existing campaign data."""
        # Business profile
        bp_result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        profile = bp_result.scalar_one_or_none()

        biz = {}
        if profile:
            biz = {
                "name": getattr(profile, "description", "") or "",
                "website": profile.website_url or "",
                "phone": profile.phone or "",
                "industry": profile.industry_classification or "",
                "services": profile.services_json or [],
                "locations": profile.locations_json or [],
                "usps": profile.usp_json or [],
                "offers": profile.offers_json or [],
                "trust_signals": profile.trust_signals_json or [],
                "brand_voice": profile.brand_voice_json or {},
                "city": profile.city or "",
                "state": profile.state or "",
                "service_radius_miles": profile.service_radius_miles or 40,
                "years_experience": profile.years_experience or 0,
                "google_rating": profile.google_rating or 0,
                "review_count": profile.review_count or 0,
                "license_info": profile.license_info or "",
                "address": profile.address or "",
                "primary_goal": profile.primary_conversion_goal or "calls",
                "avg_ticket": profile.avg_ticket_estimate or 0,
            }

        # Competitor intel
        competitor_summary = {}
        try:
            from app.services.competitor_intel_service import CompetitorIntelService
            comp_svc = CompetitorIntelService(self.db, self.tenant_id, self.customer_id)
            competitor_summary = await comp_svc.get_market_summary()
        except Exception as e:
            logger.warning("Could not load competitor intel", error=str(e))

        return {
            "business": biz,
            "account": account_context,
            "competitors": competitor_summary,
        }

    # ── PROGRESS MESSAGES ────────────────────────────────────────

    async def _emit_progress(self, agent_name: str, status: str, detail: str):
        """Insert a progress message into the conversation."""
        if not self.conversation_id:
            return
        msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=self.conversation_id,
            role="assistant",
            content=f"{agent_name}: {detail}",
            structured_payload={
                "type": "pipeline_progress",
                "agent": agent_name,
                "status": status,
                "detail": detail,
            },
        )
        self.db.add(msg)
        try:
            await self.db.flush()
        except Exception:
            pass  # Non-critical if progress message fails

    # ── CLAUDE API HELPER ────────────────────────────────────────

    async def _call_claude_json(
        self, system: str, user_msg: str,
        max_tokens: int = 4096, temperature: float = 0.5,
    ) -> Optional[Dict]:
        """Call Claude API and parse JSON response."""
        for attempt in range(3):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                    temperature=temperature,
                )
                raw = response.content[0].text.strip()
                # Strip markdown code fences
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                return json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Claude JSON parse failed", attempt=attempt, raw=raw[:200] if raw else "")
            except anthropic.APIError as e:
                logger.warning("Claude API error", attempt=attempt, error=str(e))
            except Exception as e:
                logger.warning("Claude call failed", attempt=attempt, error=str(e))
        return None

    # ── AGENT 1: STRATEGIST ──────────────────────────────────────

    async def _agent_strategist(self, context: Dict, user_prompt: str) -> Optional[Dict]:
        biz = context["business"]
        account = context["account"]
        competitors = context.get("competitors", {})

        # Format existing campaigns for context
        campaigns_text = "No existing campaigns found."
        if account.get("campaigns"):
            lines = []
            for c in account["campaigns"][:10]:
                lines.append(f"  [{c.get('status', '?')}] {c.get('name', '?')} \u2014 Budget:${c.get('budget_daily', '?')}/day | Cost:${c.get('cost', 0):.0f} | Conv:{c.get('conversions', 0)} | CPA:${c.get('cpa', 0):.0f}")
            campaigns_text = "\n".join(lines)

        system = """You are a senior Google Ads strategist. You're designing the architecture for a new campaign.

Your job is to make ONE set of decisions:
- What type of campaign (SEARCH, CALL, PERFORMANCE_MAX)
- What services to target (each becomes its own ad group for tight theming)
- What budget and bidding strategy
- Campaign naming convention
- What the strategic angle is (why THIS campaign, why NOW)

Think step by step:
1. What does the user actually want? Parse their intent carefully.
2. Look at existing campaigns — what's already covered? Don't duplicate. Fill gaps.
3. What services would be MOST profitable? Consider the business's specialties.
4. What budget makes sense given the competitive landscape and ticket size?
5. Is this a SEARCH campaign (intent-driven) or CALL campaign (emergency/mobile)?

Be SPECIFIC. Don't be generic. If the user says "BMW specialized services" and the business is an automotive locksmith, think about what BMW owners actually search for: FRM repair, key programming, comfort access, CAS module, coding. These are HIGH-TICKET services ($500-2000+).

Respond with ONLY valid JSON."""

        user_msg = f"""USER REQUEST: "{user_prompt}"

BUSINESS CONTEXT:
  Name: {biz.get('name', 'Unknown')}
  Industry: {biz.get('industry', 'Unknown')}
  Services offered: {json.dumps(biz.get('services', []))}
  Locations: {biz.get('city', '')}, {biz.get('state', '')} (radius: {biz.get('service_radius_miles', 40)} miles)
  Avg ticket: ${biz.get('avg_ticket', 0)}
  Primary goal: {biz.get('primary_goal', 'calls')}
  Phone: {biz.get('phone', '')}
  Website: {biz.get('website', '')}

EXISTING CAMPAIGNS:
{campaigns_text}

COMPETITIVE LANDSCAPE:
  Dominant themes: {json.dumps(competitors.get('dominant_themes', []))}
  Opportunity gaps: {json.dumps(competitors.get('opportunity_gaps', []))}
  Top competitors: {json.dumps([c.get('domain', '') for c in competitors.get('top_competitors', [])[:5]])}

Return this JSON structure:
{{
  "campaign_name": "A.X | [Service Theme] | [Location]",
  "campaign_type": "SEARCH" or "CALL",
  "objective": "calls" or "leads",
  "services": ["Service 1", "Service 2", "Service 3"],
  "locations": ["City 1", "City 2"],
  "budget_daily": 50,
  "budget_micros": 50000000,
  "bidding_strategy": "MAXIMIZE_CONVERSIONS",
  "target_cpa_micros": 0,
  "reasoning": "2-3 sentences on WHY these choices",
  "overlap_risk": "none" or "low" or "high — explain what overlaps",
  "profit_potential": "Estimated ticket size and margin for these services"
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=2048, temperature=0.4)

    # ── AGENT 2: KEYWORD RESEARCH ────────────────────────────────

    async def _agent_keyword_research(self, context: Dict, strategy: Dict) -> Optional[Dict]:
        biz = context["business"]
        competitors = context.get("competitors", {})
        services = strategy.get("services", [])
        locations = strategy.get("locations", biz.get("locations", []))

        system = """You are a Google Ads keyword research expert with deep knowledge of search intent.

Your job: build a COMPREHENSIVE keyword list for a Google Ads campaign. You think about keywords the way a real searcher types — not marketing jargon, but actual queries people use when they need this service.

CRITICAL RULES:
1. SEGMENT BY SERVICE: Each service becomes its own ad group. Keywords MUST be unique per service. NO keyword can appear in two services — this causes internal competition and tanks Quality Score.

2. TIER YOUR KEYWORDS BY INTENT:
   - EMERGENCY (highest bid): "emergency [X]", "[X] help now", "24/7 [X]" — EXACT match
   - HIGH INTENT (ready to buy): "[X] near me", "[X] service", "hire [X]" — EXACT match
   - MEDIUM INTENT (researching): "best [X]", "[X] cost", "how much [X]" — PHRASE match
   - LOCAL (geo-modified): "[X] in [city]", "[city] [X]" — EXACT match
   - SERVICE-SPECIFIC (long-tail): problem-specific queries real people type — PHRASE match

3. THINK LIKE THE SEARCHER: Someone whose BMW key stopped working doesn't search "BMW key programming" — they search "bmw key not working", "lost bmw key", "bmw key fob dead". Include PROBLEM-BASED keywords, not just service-based ones.

4. NEGATIVES ARE CRITICAL: Block DIY, jobs, training, free, complaints, tools, parts-only, used. Also block adjacent services you DON'T offer.

5. MINIMUM: 20 keywords per service, 20 negatives total. More is better for coverage.

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN STRATEGY:
  Type: {strategy.get('campaign_type', 'SEARCH')}
  Services (each = 1 ad group): {json.dumps(services)}
  Target locations: {json.dumps(locations)}

BUSINESS:
  Industry: {biz.get('industry', '')}
  Full service list: {json.dumps(biz.get('services', []))}

COMPETITOR THEMES (what they bid on):
  {json.dumps(competitors.get('dominant_themes', []))}
GAPS (what they DON'T target):
  {json.dumps(competitors.get('opportunity_gaps', []))}

Return this JSON:
{{
  "keywords": [
    {{"text": "keyword phrase", "match_type": "EXACT"|"PHRASE", "tier": "emergency"|"high"|"medium"|"local"|"service", "service": "exact service name"}},
    ...
  ],
  "negatives": [
    {{"text": "negative term", "match_type": "PHRASE"}},
    ...
  ],
  "total_keywords": N,
  "total_negatives": N,
  "tiers": {{"emergency": N, "high": N, "medium": N, "local": N, "service": N}},
  "keyword_rationale": "Brief strategy explanation"
}}

IMPORTANT: Every keyword MUST have a "service" field matching exactly one of: {json.dumps(services)}"""

        return await self._call_claude_json(system, user_msg, max_tokens=4096, temperature=0.6)

    # ── AGENT 3: TARGETING ───────────────────────────────────────

    async def _agent_targeting(self, context: Dict, strategy: Dict) -> Optional[Dict]:
        biz = context["business"]

        system = """You are a Google Ads targeting specialist. You configure geo-targeting, device bids, and ad schedules to maximize ROI.

Think about the BUSINESS TYPE to make targeting decisions:
- Emergency services (locksmith, plumber, towing): 24/7 schedule, heavy mobile bid boost (+30-50%), radius targeting
- Professional services (lawyer, dentist): business hours + evenings, moderate mobile boost, city-level targeting
- E-commerce: all hours, balanced device bids, broader geo

For device bids, think about HOW people search for this service:
- If they're locked out of their car, they're on their PHONE → mobile +40%
- If they're researching BMW repair options, they might be on desktop → balanced
- Tablets are rarely used for urgent searches → usually neutral or negative

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN:
  Type: {strategy.get('campaign_type', 'SEARCH')}
  Services: {json.dumps(strategy.get('services', []))}
  Objective: {strategy.get('objective', 'calls')}

BUSINESS LOCATION:
  City: {biz.get('city', '')}, {biz.get('state', '')}
  Address: {biz.get('address', '')}
  Service radius: {biz.get('service_radius_miles', 40)} miles
  Target locations from strategy: {json.dumps(strategy.get('locations', []))}

Return this JSON:
{{
  "geo": {{
    "type": "radius" or "cities",
    "locations": ["City 1", "City 2"],
    "radius_miles": 40,
    "reasoning": "Why this geo config"
  }},
  "device_bids": {{
    "mobile_bid_adj": 30,
    "desktop_bid_adj": 0,
    "tablet_bid_adj": -20,
    "reasoning": "Why these device adjustments"
  }},
  "schedule": {{
    "all_day": true,
    "peak_adjustments": [
      {{"days": ["MONDAY", "TUESDAY"], "hours": "8-20", "bid_adj": 15}},
      {{"days": ["SATURDAY", "SUNDAY"], "hours": "18-23", "bid_adj": 25}}
    ],
    "reasoning": "Why this schedule"
  }}
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=1536, temperature=0.4)

    # ── AGENT 4: EXTENSIONS ──────────────────────────────────────

    async def _agent_extensions(self, context: Dict, strategy: Dict) -> Optional[Dict]:
        biz = context["business"]
        services = strategy.get("services", [])

        system = """You are a Google Ads extensions specialist. You create sitelinks, callouts, and structured snippets that boost CTR and Ad Rank.

RULES:
- Sitelinks: text max 25 chars, description1 max 35 chars, description2 max 35 chars. Need 4-6.
  Each sitelink should deep-link to a REAL page on the website. Use the website URL to construct logical paths.
  Good: "/services/bmw-programming", "/about", "/contact", "/reviews"
  Bad: "/sitelink1", generic pages

- Callouts: max 25 chars each. Need 6-10. Punchy trust signals. No CTAs (those go in headlines).
  Good: "Licensed & Insured", "24/7 Available", "Same-Day Service"
  Bad: "Call Now", "Click Here", "Best Service Ever"

- Structured snippets: header must be one of Google's approved headers (Services, Brands, Types, etc.)
  Values should be specific services, not generic descriptions.

- Call extension: include the business phone number.

COUNT EVERY CHARACTER. Google rejects assets that exceed limits.

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN:
  Services: {json.dumps(services)}
  Business: {biz.get('name', '')}
  Website: {biz.get('website', '')}
  Phone: {biz.get('phone', '')}
  USPs: {json.dumps(biz.get('usps', []))}
  Offers: {json.dumps(biz.get('offers', []))}
  Trust signals: {json.dumps(biz.get('trust_signals', []))}
  Years experience: {biz.get('years_experience', 0)}
  Google rating: {biz.get('google_rating', 0)} ({biz.get('review_count', 0)} reviews)
  License: {biz.get('license_info', '')}

Return this JSON:
{{
  "sitelinks": [
    {{"link_text": "text (max 25)", "final_url": "https://...", "description1": "desc (max 35)", "description2": "desc (max 35)"}},
    ...
  ],
  "callouts": ["text (max 25)", ...],
  "structured_snippets": {{
    "header": "Services",
    "values": ["Service 1", "Service 2", ...]
  }},
  "call_extension": {{
    "phone": "{biz.get('phone', '')}",
    "country_code": "US"
  }}
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=2048, temperature=0.5)

    # ── AGENT 5: AD COPY ─────────────────────────────────────────

    async def _agent_ad_copy(self, context: Dict, strategy: Dict, keywords: Dict) -> Optional[Dict]:
        biz = context["business"]
        competitors = context.get("competitors", {})
        services = strategy.get("services", [])

        # Group keywords by service for per-ad-group context
        kw_by_service = {}
        for kw in keywords.get("keywords", []):
            svc = kw.get("service", "")
            kw_by_service.setdefault(svc, []).append(kw["text"])

        services_context = []
        for svc in services:
            svc_kws = kw_by_service.get(svc, [])[:15]
            services_context.append(f"  AD GROUP: {svc}\n    Keywords: {', '.join(svc_kws)}")

        system = f"""You are an elite Google Ads RSA (Responsive Search Ad) copywriter. You write ads that convert.

You are writing ads for: {biz.get('name', 'this business')}
Industry: {biz.get('industry', '')}
Phone: {biz.get('phone', '')}
Website: {biz.get('website', '')}

YOUR APPROACH — Think like a customer, not a marketer:
Someone searching for "{services[0] if services else 'this service'}" is probably:
- In a stressful situation (locked out, car won't start, module failed)
- Comparing options quickly on their phone
- Looking for PROOF you can actually do this (credentials, experience, reviews)
- Price-sensitive but willing to pay for expertise on premium/specialized work

HEADLINE STRATEGY (15 per ad group, each max 30 chars):
H1-H3: Keyword match — must contain the primary service term. Pin H1 to position 1.
H4-H5: Location — include the target city/area. Geo-headlines get 15-25% higher CTR.
H6-H8: Trust proof — use REAL trust signals: "{biz.get('google_rating', 0)}\u2605 Rating", "{biz.get('years_experience', 0)}+ Years Exp", license info.
H9-H10: USP — translate unique selling points into punchy headlines.
H11-H12: Offer/CTA — "Free Estimate", "Call Now", specific offers.
H13-H14: Urgency — "Available Now", "Same-Day Service", "30-Min Response".
H15: Brand name — "{biz.get('name', '')}" if it fits.

DESCRIPTION STRATEGY (4 per ad group, each max 90 chars):
D1: Problem \u2192 Solution \u2192 CTA (pin to position 1)
D2: Trust proof + differentiator
D3: Offer + urgency
D4: Local authority + reassurance

CHARACTER LIMITS ARE ABSOLUTE:
- Headlines: EXACTLY 30 characters max. Not 31. Count carefully.
- Descriptions: EXACTLY 90 characters max. Count carefully.
- If the business name is too long, abbreviate it.

NEVER USE: "Best", "#1", "Top Rated" (without proof), "Quality Service", "Great Prices" — these are generic garbage that tanks CTR.
ALWAYS USE: Specific numbers, credentials, real trust signals, the actual service name.

Competitor gaps to exploit: {json.dumps(competitors.get('opportunity_gaps', []))}

Respond with ONLY valid JSON."""

        user_msg = f"""CAMPAIGN: {strategy.get('campaign_name', 'New Campaign')}
LOCATIONS: {json.dumps(strategy.get('locations', []))}
BUSINESS USPs: {json.dumps(biz.get('usps', []))}
OFFERS: {json.dumps(biz.get('offers', []))}
TRUST SIGNALS: {json.dumps(biz.get('trust_signals', []))}

AD GROUPS AND THEIR KEYWORDS:
{chr(10).join(services_context)}

For EACH ad group, generate a complete RSA. Return this JSON:
{{
  "ad_groups": [
    {{
      "service": "exact service name",
      "headlines": ["H1", "H2", ..., "H15"],
      "descriptions": ["D1", "D2", "D3", "D4"],
      "pinning": {{
        "headline_pins": {{"1": 0}},
        "description_pins": {{"1": 0}}
      }},
      "final_url": "{biz.get('website', 'https://example.com')}/relevant-page",
      "display_path": ["Path1", "Path2"]
    }},
    ...
  ]
}}

CRITICAL: Generate ads for ALL {len(services)} services: {json.dumps(services)}
Each ad group MUST have exactly 15 headlines and 4 descriptions."""

        return await self._call_claude_json(system, user_msg, max_tokens=4096, temperature=0.7)

    # ── AGENT 6: QA ──────────────────────────────────────────────

    async def _agent_qa(self, spec: Dict, context: Dict, user_prompt: str) -> Optional[Dict]:
        system = """You are a Google Ads compliance auditor and quality reviewer. You check campaigns before they go live.

CHECK THESE THINGS:
1. Character limits: headlines max 30, descriptions max 90, sitelink text max 25, sitelink descriptions max 35, callouts max 25
2. Minimum counts: at least 3 headlines per ad (Google requires minimum 3), at least 2 descriptions (minimum 2), RSA best practice is 15 headlines + 4 descriptions
3. No duplicate headlines within the same ad group
4. Every ad has final_urls set (not empty)
5. Keywords are segmented — no keyword appears in multiple ad groups
6. Negative keywords don't accidentally block own keywords
7. Budget is reasonable (not $0, not $10000/day for a local business)
8. Sitelink URLs look real (not placeholder URLs)
9. Phone number format is valid if present
10. Campaign name follows conventions

For each issue, provide:
- severity: "critical" (will fail to deploy) vs "warning" (suboptimal but works)
- field: which part of the spec has the issue
- message: what's wrong
- fix: the corrected value (so we can auto-apply it)

Score 0-100 based on campaign quality. 90+ is excellent. Below 70 needs correction.

Respond with ONLY valid JSON."""

        user_msg = f"""ORIGINAL USER REQUEST: "{user_prompt}"

FULL CAMPAIGN SPEC TO REVIEW:
{json.dumps(spec, indent=2)}

Return this JSON:
{{
  "score": 85,
  "grade": "B+",
  "issues": [
    {{"severity": "critical"|"warning", "field": "ad_groups[0].ads[0].headlines[2]", "message": "Headline exceeds 30 chars", "fix": "Shortened Headline"}},
    ...
  ],
  "fixes": {{
    "field.path": "corrected value"
  }},
  "approved": true,
  "summary": "Brief assessment of campaign quality"
}}"""

        return await self._call_claude_json(system, user_msg, max_tokens=2048, temperature=0.2)

    # ── SPEC ASSEMBLY ────────────────────────────────────────────

    def _assemble_spec(
        self,
        strategy: Dict,
        keywords: Dict,
        ad_copy: Dict,
        targeting: Dict,
        extensions: Dict,
    ) -> Dict[str, Any]:
        """Map all agent outputs into the deploy_full_campaign spec format."""
        services = strategy.get("services", [])

        # Group keywords by service
        kw_by_service: Dict[str, List] = {}
        for kw in keywords.get("keywords", []):
            svc = kw.get("service", "")
            kw_by_service.setdefault(svc, []).append({
                "text": kw["text"],
                "match_type": kw.get("match_type", "PHRASE"),
            })

        # Global negatives
        negatives = [n.get("text", "") for n in keywords.get("negatives", []) if n.get("text")]

        # Build ad groups by merging keywords + ad copy per service
        ad_groups = []
        ad_copy_by_service = {}
        for ag in ad_copy.get("ad_groups", []):
            ad_copy_by_service[ag.get("service", "")] = ag

        for svc in services:
            svc_keywords = kw_by_service.get(svc, [])
            svc_copy = ad_copy_by_service.get(svc, {})

            ad_group = {
                "name": f"{svc} \u2014 {strategy.get('locations', ['DFW'])[0] if strategy.get('locations') else 'All Areas'}",
                "keywords": svc_keywords,
                "ads": [{
                    "headlines": svc_copy.get("headlines", []),
                    "descriptions": svc_copy.get("descriptions", []),
                    "final_url": svc_copy.get("final_url", strategy.get("website", "")),
                    "final_urls": [svc_copy.get("final_url", strategy.get("website", ""))],
                }],
                "negative_keywords": negatives,
            }
            ad_groups.append(ad_group)

        # Assemble the full spec
        geo = targeting.get("geo", {})
        device_bids = targeting.get("device_bids", {})

        return {
            "campaign": {
                "name": strategy.get("campaign_name", "AI Campaign"),
                "budget_micros": strategy.get("budget_micros", 50_000_000),
                "bidding_strategy": strategy.get("bidding_strategy", "MAXIMIZE_CONVERSIONS"),
                "target_cpa_micros": strategy.get("target_cpa_micros", 0),
                "channel_type": strategy.get("campaign_type", "SEARCH"),
                "network": "SEARCH",
            },
            "ad_groups": ad_groups,
            "sitelinks": extensions.get("sitelinks", []),
            "callouts": extensions.get("callouts", []),
            "structured_snippets": extensions.get("structured_snippets", {}),
            # Store metadata for display
            "_pipeline_metadata": {
                "strategy": strategy,
                "targeting": targeting,
                "keyword_stats": keywords.get("tiers", {}),
                "qa_score": None,  # Filled by QA agent
            },
        }

    # ── QA FIX APPLICATION ───────────────────────────────────────

    def _apply_qa_fixes(self, spec: Dict, qa_result: Dict) -> Dict:
        """Apply QA agent corrections to the assembled spec."""
        if not qa_result:
            return spec

        # Store QA score in metadata
        if "_pipeline_metadata" in spec:
            spec["_pipeline_metadata"]["qa_score"] = qa_result.get("score")

        # Apply character limit fixes
        for issue in qa_result.get("issues", []):
            if issue.get("severity") != "critical":
                continue
            fix = issue.get("fix")
            field = issue.get("field", "")
            if not fix or not field:
                continue

            # Auto-truncate headlines that are too long
            if "headlines" in field:
                try:
                    parts = field.replace("]", "").replace("[", ".").split(".")
                    for ag in spec.get("ad_groups", []):
                        for ad in ag.get("ads", []):
                            for i, h in enumerate(ad.get("headlines", [])):
                                if len(h) > 30:
                                    ad["headlines"][i] = h[:30]
                except Exception:
                    pass

            # Auto-truncate descriptions that are too long
            if "descriptions" in field:
                try:
                    for ag in spec.get("ad_groups", []):
                        for ad in ag.get("ads", []):
                            for i, d in enumerate(ad.get("descriptions", [])):
                                if len(d) > 90:
                                    ad["descriptions"][i] = d[:90]
                except Exception:
                    pass

        # Always do a safety pass on character limits
        for ag in spec.get("ad_groups", []):
            for ad in ag.get("ads", []):
                ad["headlines"] = [h[:30] for h in ad.get("headlines", [])]
                ad["descriptions"] = [d[:90] for d in ad.get("descriptions", [])]

        # Truncate sitelink fields
        for sl in spec.get("sitelinks", []):
            if sl.get("link_text"):
                sl["link_text"] = sl["link_text"][:25]
            if sl.get("description1"):
                sl["description1"] = sl["description1"][:35]
            if sl.get("description2"):
                sl["description2"] = sl["description2"][:35]

        # Truncate callouts
        spec["callouts"] = [c[:25] for c in spec.get("callouts", [])]

        return spec

    # ── FALLBACK ─────────────────────────────────────────────────

    def _fallback_spec(self, user_prompt: str, context: Dict) -> Dict:
        """Minimal fallback spec if the pipeline fails entirely."""
        biz = context.get("business", {})
        return {
            "campaign": {
                "name": f"AI Campaign \u2014 {user_prompt[:50]}",
                "budget_micros": 50_000_000,
                "bidding_strategy": "MAXIMIZE_CONVERSIONS",
                "channel_type": "SEARCH",
                "network": "SEARCH",
            },
            "ad_groups": [],
            "sitelinks": [],
            "callouts": [],
            "structured_snippets": {},
            "_pipeline_error": "Pipeline failed — please try again or create manually",
        }
