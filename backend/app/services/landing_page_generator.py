"""
Landing Page Generator — AI agent pipeline that creates high-converting
landing pages with 3 variants (Emergency, Savings, Expert).

Pipeline agents:
  1. Landing Page Strategist — offer angle, tone, CTA strategy
  2. Variant Generator — 3 complete variants with copy, trust, CRO
  3. Image Generator — hero images via SEOpix/DALL-E
  4. QA Reviewer — validates keyword match, CTAs, trust signals, phone
     Auto-fixes issues if quality score < 70 (one correction round)
"""
import asyncio
import json
import re
import uuid
import time
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.landing_page import LandingPage, LandingPageVariant
from app.services.operator.llm_fallback_service import LLMFallbackService

logger = structlog.get_logger()

# Minimum QA score to pass without auto-fix
QA_PASS_THRESHOLD = 70
# Maximum correction rounds
MAX_FIX_ROUNDS = 1


class LandingPageGenerator:
    """AI-powered landing page generation with Claude Opus + GPT-4o fallback."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.llm = LLMFallbackService()
        # Landing pages are quality-critical — Opus produces significantly
        # better copy, keyword-headline matching, and variant differentiation.
        # Cost: ~$0.30 per page × 2-3 calls = $0.60-0.90 per campaign.
        # A bad landing page costs $10+/day in wasted ad spend.
        self.model = "claude-opus-4-6"

    async def generate(
        self,
        service: str,
        location: str = "",
        industry: str = "",
        business_name: str = "",
        phone: str = "",
        website: str = "",
        usps: List[str] = None,
        offers: List[str] = None,
        campaign_keywords: List[str] = None,
        campaign_headlines: List[str] = None,
        trust_signals: List[str] = None,
        description: str = "",
        constraints: Dict[str, Any] = None,
        image_engine: str = "google",
        image_model: str = "",
    ) -> Dict[str, Any]:
        """
        Full pipeline: strategy → copy → trust → CRO audit → 3 variants → save.
        Returns the LandingPage record with variants.
        """
        if not settings.ANTHROPIC_API_KEY and not settings.OPENAI_API_KEY:
            return {"error": "AI not configured (no API key)"}

        def _as_list(val):
            """Coerce value to list — handles None, dict, and other iterables."""
            if val is None:
                return []
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return list(val.values()) if val else []
            try:
                return list(val)
            except (TypeError, ValueError):
                return []

        usps = _as_list(usps)
        offers = _as_list(offers)
        campaign_keywords = _as_list(campaign_keywords)
        campaign_headlines = _as_list(campaign_headlines)
        trust_signals = _as_list(trust_signals)
        constraints = constraints or {}

        context = {
            "service": service,
            "location": location,
            "industry": industry,
            "business_name": business_name,
            "phone": phone,
            "website": website,
            "usps": usps,
            "offers": offers,
            "campaign_keywords": campaign_keywords,
            "campaign_headlines": campaign_headlines,
            "trust_signals": trust_signals,
            "description": description,
            "constraints": constraints,
        }

        # Agent 1: Strategy
        strategy = await self._agent_strategist(context)

        # Agent 2: Copy + Trust + CRO (combined for efficiency)
        variants = await self._agent_variant_generator(context, strategy)

        if not variants or not isinstance(variants, list) or len(variants) == 0:
            return {"error": "AI failed to generate landing page variants"}

        # Agent 3: QA Reviewer — validates and auto-fixes each variant
        variants = await self._agent_qa_reviewer(variants, context, strategy)

        # Agent 4: Generate hero images for each variant
        variants = await self._generate_variant_images(
            variants, service=service, business_name=business_name,
            industry=industry, location=location,
            engine=image_engine, engine_model=image_model,
        )

        # Save to DB
        _svc_part = re.sub(r"[^a-z0-9-]", "", service.lower().replace(" ", "-"))
        _loc_part = re.sub(r"[^a-z0-9-]", "", location.lower().replace(" ", "-"))
        slug = f"{_svc_part}-{_loc_part}-{uuid.uuid4().hex[:6]}"
        slug = slug.replace("--", "-").strip("-")[:250]

        lp = LandingPage(
            tenant_id=self.tenant_id,
            name=f"{service} — {location}" if location else service,
            slug=slug,
            service=service,
            location=location,
            status="preview",
            page_type="service",
            is_ai_generated=True,
            strategy_json=strategy,
            content_json=variants[0].get("content", {}) if variants else {},
            style_json=strategy.get("style", {}),
            seo_json=strategy.get("seo", {}),
        )
        self.db.add(lp)
        await self.db.flush()

        variant_records = []
        for i, v in enumerate(variants[:3]):
            vr = LandingPageVariant(
                landing_page_id=lp.id,
                variant_key=chr(65 + i),  # A, B, C
                variant_name=v.get("name", f"Variant {chr(65 + i)}"),
                content_json=v.get("content", {}),
                is_active=True,
            )
            self.db.add(vr)
            variant_records.append(vr)

        await self.db.commit()

        return {
            "landing_page_id": lp.id,
            "slug": lp.slug,
            "name": lp.name,
            "status": lp.status,
            "strategy": strategy,
            "variants": [
                {
                    "id": vr.id,
                    "key": vr.variant_key,
                    "name": vr.variant_name,
                    "content": vr.content_json,
                    "qa_score": variants[i].get("qa_score") if i < len(variants) else None,
                    "qa_issues": variants[i].get("qa_issues", []) if i < len(variants) else [],
                    "qa_fixed": variants[i].get("qa_fixed", False) if i < len(variants) else False,
                }
                for i, vr in enumerate(variant_records)
            ],
        }

    async def ai_edit_variant(
        self,
        variant_content: Dict,
        edit_prompt: str,
        strategy: Dict = None,
        business_context: Dict = None,
    ) -> Dict[str, Any]:
        """Apply a prompt-based edit to a landing page variant's content.
        Handles everything from small tweaks to full redesigns."""
        if not settings.ANTHROPIC_API_KEY and not settings.OPENAI_API_KEY:
            return {"error": "AI not configured"}

        business_context = business_context or {}

        system = """You are an elite landing page designer and conversion expert who creates
stunning, professional, high-converting landing pages for local service businesses.

You can handle ANY type of edit instruction — from small text changes to complete redesigns.
When the user asks to "redesign", "make professional", or requests broad changes, you should
dramatically improve the entire page: better headlines, stronger copy, more compelling CTAs,
professional structure, and polished content.

CAPABILITIES:
- Redesign entire pages with professional, modern content
- Add/update business branding (name, phone, logo references)
- Improve copy for conversions (urgency, trust, social proof)
- Restructure sections for better flow
- Add new sections (testimonials, FAQ, trust bars, service lists)
- Make pages more professional, modern, and visually compelling

RULES:
- ALWAYS return the COMPLETE updated content JSON with ALL sections
- Maintain the same JSON structure/schema as the input
- Use REAL business details provided (name, phone, city, etc.) — never placeholders
- Phone number must appear in hero CTA and footer CTA at minimum
- Every headline should be compelling and conversion-focused
- For redesigns: be bold — significantly improve headlines, copy, CTAs, and structure
- Respond ONLY with valid JSON matching the input structure"""

        # Build business identity block
        biz_lines = []
        if business_context.get("business_name"):
            biz_lines.append(f"BUSINESS NAME: {business_context['business_name']}")
        if business_context.get("phone"):
            biz_lines.append(f"PHONE: {business_context['phone']}")
        if business_context.get("website"):
            biz_lines.append(f"WEBSITE: {business_context['website']}")
        if business_context.get("city"):
            loc = business_context["city"]
            if business_context.get("state"):
                loc += f", {business_context['state']}"
            biz_lines.append(f"LOCATION: {loc}")
        if business_context.get("industry"):
            biz_lines.append(f"INDUSTRY: {business_context['industry']}")
        if business_context.get("google_rating"):
            biz_lines.append(f"GOOGLE RATING: {business_context['google_rating']} ({business_context.get('review_count', 0)} reviews)")
        if business_context.get("trust_signals"):
            ts = business_context["trust_signals"]
            if isinstance(ts, dict):
                ts_items = [f"{k}: {v}" for k, v in ts.items() if v]
            elif isinstance(ts, list):
                ts_items = ts[:6]
            else:
                ts_items = []
            if ts_items:
                biz_lines.append(f"TRUST SIGNALS: {', '.join(ts_items)}")

        biz_block = "\n".join(biz_lines) if biz_lines else "(no business profile loaded)"

        content_str = json.dumps(variant_content, indent=2)
        # Allow up to 12K chars for content (was 6K)
        if len(content_str) > 12000:
            content_str = content_str[:12000] + "\n... (truncated)"

        prompt = f"""── BUSINESS IDENTITY (use these REAL details) ──
{biz_block}

── CURRENT LANDING PAGE CONTENT ──
{content_str}

── EDIT INSTRUCTION ──
{edit_prompt}

Apply the edit instruction above. Return the COMPLETE updated content JSON.
If the instruction is a broad redesign request, make dramatic improvements across
all sections — better headlines, stronger copy, more compelling CTAs, and professional polish.
Use the real business name, phone, and details throughout."""

        result = await self._call_ai(system, prompt, temperature=0.4, max_tokens=8192)
        if not result:
            return {"error": "AI failed to apply edit"}
        return {"content": result, "edit_applied": edit_prompt}

    async def clone_landing_page(
        self,
        source_lp: "LandingPage",
        new_service: str = "",
        new_location: str = "",
        adapt_prompt: str = "",
    ) -> Dict[str, Any]:
        """Clone a landing page, optionally adapting content for a new service/location."""
        _svc_part = re.sub(r"[^a-z0-9-]", "", (new_service or source_lp.service or "page").lower().replace(" ", "-"))
        _loc_part = re.sub(r"[^a-z0-9-]", "", (new_location or source_lp.location or "local").lower().replace(" ", "-"))
        slug = f"{_svc_part}-{_loc_part}-{uuid.uuid4().hex[:6]}"
        slug = slug.replace("--", "-").strip("-")[:250]

        new_lp = LandingPage(
            tenant_id=self.tenant_id,
            name=f"{new_service or source_lp.service} — {new_location or source_lp.location}" if (new_location or source_lp.location) else (new_service or source_lp.service or source_lp.name),
            slug=slug,
            service=new_service or source_lp.service,
            location=new_location or source_lp.location,
            status="preview",
            page_type=source_lp.page_type,
            is_ai_generated=True,
            strategy_json=source_lp.strategy_json or {},
            content_json=source_lp.content_json or {},
            style_json=source_lp.style_json or {},
            seo_json=source_lp.seo_json or {},
        )
        self.db.add(new_lp)
        await self.db.flush()

        variant_records = []
        source_variants = source_lp.variants or []
        for sv in source_variants:
            content = sv.content_json or {}

            # If adapting for new service/location, use AI to rewrite
            if adapt_prompt and self.client:
                adapted = await self.ai_edit_variant(
                    content,
                    adapt_prompt or f"Adapt this landing page for '{new_service}' in '{new_location}'. Update all headlines, copy, service references, and location mentions.",
                )
                if not adapted.get("error"):
                    content = adapted["content"]

            vr = LandingPageVariant(
                landing_page_id=new_lp.id,
                variant_key=sv.variant_key,
                variant_name=sv.variant_name,
                content_json=content,
                is_active=True,
            )
            self.db.add(vr)
            variant_records.append(vr)

        await self.db.commit()

        return {
            "landing_page_id": new_lp.id,
            "slug": new_lp.slug,
            "name": new_lp.name,
            "status": new_lp.status,
            "variants": [
                {"id": vr.id, "key": vr.variant_key, "name": vr.variant_name, "content": vr.content_json}
                for vr in variant_records
            ],
        }

    # ── Agent 3: QA Reviewer ────────────────────────────────────────

    async def _agent_qa_reviewer(
        self,
        variants: List[Dict],
        context: Dict,
        strategy: Dict,
    ) -> List[Dict]:
        """
        QA Reviewer agent — Claude Opus validates each variant against
        Google Ads landing page best practices BEFORE showing to user.

        Checks:
        1. Keyword-headline match (H1 must contain campaign keywords)
        2. Phone number presence (hero CTA + footer CTA minimum)
        3. Business name in headline
        4. Location mention in hero
        5. Trust signals match real data (not fabricated)
        6. CTA clarity and above-fold placement
        7. No placeholder text (lorem ipsum, [PLACEHOLDER], etc.)
        8. Review authenticity (realistic, mentions service)

        If score < 70, auto-fixes the variant with one correction round.
        """
        reviewed_variants = []

        # Review all variants concurrently
        review_tasks = [
            self._review_single_variant(v, context, strategy)
            for v in variants
        ]
        reviews = await asyncio.gather(*review_tasks, return_exceptions=True)

        for i, (variant, review) in enumerate(zip(variants, reviews)):
            if isinstance(review, Exception):
                logger.warning("QA review failed for variant", variant=variant.get("name"), error=str(review))
                variant["qa_score"] = None
                variant["qa_issues"] = []
                reviewed_variants.append(variant)
                continue

            score = review.get("score", 100)
            issues = review.get("issues", [])
            variant["qa_score"] = score
            variant["qa_issues"] = issues

            logger.info(
                "QA review complete",
                variant=variant.get("name"),
                score=score,
                issue_count=len(issues),
            )

            # Auto-fix if below threshold
            if score < QA_PASS_THRESHOLD and issues:
                logger.info(
                    "QA score below threshold — running auto-fix",
                    variant=variant.get("name"),
                    score=score,
                    threshold=QA_PASS_THRESHOLD,
                )
                fixed_variant = await self._auto_fix_variant(
                    variant, issues, context, strategy
                )
                if fixed_variant:
                    # Re-review after fix
                    re_review = await self._review_single_variant(
                        fixed_variant, context, strategy
                    )
                    if not isinstance(re_review, Exception):
                        fixed_variant["qa_score"] = re_review.get("score", score)
                        fixed_variant["qa_issues"] = re_review.get("issues", [])
                        logger.info(
                            "QA re-review after fix",
                            variant=fixed_variant.get("name"),
                            old_score=score,
                            new_score=fixed_variant["qa_score"],
                        )
                    reviewed_variants.append(fixed_variant)
                    continue

            reviewed_variants.append(variant)

        return reviewed_variants

    async def _review_single_variant(
        self,
        variant: Dict,
        context: Dict,
        strategy: Dict,
    ) -> Dict:
        """Review a single variant and return score + issues."""
        system = """You are a Google Ads landing page QA specialist.
You validate landing pages against strict conversion and Quality Score criteria.
You are ruthlessly precise — you catch every issue that would hurt Quality Score or conversion rate.

Respond ONLY with valid JSON."""

        content = variant.get("content", {})
        content_str = json.dumps(content, indent=1)
        if len(content_str) > 8000:
            content_str = content_str[:8000] + "\n...(truncated)"

        prompt = f"""Review this landing page variant for Google Ads Quality Score and conversion readiness.

── VARIANT ──
Name: {variant.get('name', 'Unknown')}
Angle: {variant.get('angle', 'Unknown')}
Content:
{content_str}

── CAMPAIGN CONTEXT (what must be reflected) ──
Business Name: {context.get('business_name', 'N/A')}
Phone: {context.get('phone', 'N/A')}
Service: {context.get('service', 'N/A')}
Location: {context.get('location', 'N/A')}
Campaign Keywords: {json.dumps(context.get('campaign_keywords', [])[:10])}
Campaign Headlines: {json.dumps(context.get('campaign_headlines', [])[:5])}
Trust Signals (REAL — must match): {json.dumps(context.get('trust_signals', [])[:8])}

── QA CHECKLIST (score each 0-10) ──
1. KEYWORD_HEADLINE_MATCH: Does H1 contain exact campaign keywords? (weight: 25%)
2. PHONE_PRESENCE: Is real phone in hero CTA + at least one more place? (weight: 15%)
3. BUSINESS_NAME: Is the real business name in headline/hero? (weight: 10%)
4. LOCATION_MENTION: Is the real city/location in hero area? (weight: 10%)
5. TRUST_ACCURACY: Are trust signals real (from context) not fabricated? (weight: 15%)
6. CTA_CLARITY: Is the primary CTA clear, compelling, above fold? (weight: 10%)
7. NO_PLACEHOLDERS: No lorem ipsum, [PLACEHOLDER], "Your Business", generic text? (weight: 10%)
8. REVIEW_QUALITY: Do reviews feel authentic, mention specific service? (weight: 5%)

Return JSON:
{{
  "score": 0-100 (weighted average of checks),
  "checks": {{
    "keyword_headline_match": {{"score": 0-10, "detail": "what was found/missing"}},
    "phone_presence": {{"score": 0-10, "detail": "..."}},
    "business_name": {{"score": 0-10, "detail": "..."}},
    "location_mention": {{"score": 0-10, "detail": "..."}},
    "trust_accuracy": {{"score": 0-10, "detail": "..."}},
    "cta_clarity": {{"score": 0-10, "detail": "..."}},
    "no_placeholders": {{"score": 0-10, "detail": "..."}},
    "review_quality": {{"score": 0-10, "detail": "..."}}
  }},
  "issues": [
    {{"severity": "critical"|"major"|"minor", "check": "keyword_headline_match", "problem": "H1 says 'Professional Service' but should contain 'car locksmith near me'", "fix": "Change H1 to 'Fast Car Locksmith Near Me — Call Now'"}},
    ...
  ],
  "pass": true|false,
  "summary": "1 sentence overall assessment"
}}"""

        # Use Sonnet for QA review — fast, cheaper, still catches issues well
        result = await self.llm.call_json(
            system=system,
            user_msg=prompt,
            max_tokens=2000,
            temperature=0.2,
            preferred_model="claude-sonnet-4-20250514",
        )
        if result and result.get("data"):
            return result["data"]
        return {"score": 100, "issues": [], "pass": True, "summary": "Review unavailable"}

    async def _auto_fix_variant(
        self,
        variant: Dict,
        issues: List[Dict],
        context: Dict,
        strategy: Dict,
    ) -> Optional[Dict]:
        """Auto-fix a variant based on QA issues. Returns the fixed variant or None."""
        content = variant.get("content", {})

        # Build fix instructions from issues
        fix_instructions = []
        for issue in issues:
            severity = issue.get("severity", "minor")
            if severity in ("critical", "major"):
                fix_instructions.append(
                    f"- [{severity.upper()}] {issue.get('check', '')}: {issue.get('fix', issue.get('problem', ''))}"
                )

        if not fix_instructions:
            return None

        system = """You are a Google Ads landing page QA fixer.
You receive a landing page variant and a list of QA issues that MUST be fixed.
Apply ALL fixes precisely. Do not change anything that isn't broken.
Return the COMPLETE updated content JSON.
Respond ONLY with valid JSON."""

        prompt = f"""Fix these QA issues in the landing page variant.

── BUSINESS CONTEXT (use these REAL details) ──
Business: {context.get('business_name', 'N/A')}
Phone: {context.get('phone', 'N/A')}
Service: {context.get('service', 'N/A')}
Location: {context.get('location', 'N/A')}
Keywords: {json.dumps(context.get('campaign_keywords', [])[:10])}

── CURRENT CONTENT ──
{json.dumps(content, indent=1)[:10000]}

── QA ISSUES TO FIX ──
{chr(10).join(fix_instructions)}

Apply all fixes. Return the COMPLETE content JSON with fixes applied.
The hero headline MUST contain the campaign keywords.
The phone number MUST be {context.get('phone', 'N/A')}.
The business name MUST be {context.get('business_name', 'N/A')}.
The location MUST be mentioned: {context.get('location', 'N/A')}."""

        result = await self._call_ai(system, prompt, temperature=0.3, max_tokens=6000)
        if result:
            fixed_variant = {**variant, "content": result, "qa_fixed": True}
            logger.info("Auto-fix applied", variant=variant.get("name"), fixes=len(fix_instructions))
            return fixed_variant
        return None

    # ── Agent 4: Image Generation ────────────────────────────────────

    async def _generate_variant_images(
        self,
        variants: List[Dict],
        service: str = "",
        business_name: str = "",
        industry: str = "",
        location: str = "",
        engine: str = "google",
        engine_model: str = "",
    ) -> List[Dict]:
        """Generate real AI images for each variant's hero section using SEOpix.

        Args:
            engine: Image engine — 'google' (default, Nano Banana), 'dalle', 'flux', 'stability'
            engine_model: Sub-model override (e.g. 'gemini-2.5-flash-image', 'flux-pro')
        """
        from app.integrations.image_generator.client import ImageGeneratorClient

        img_client = ImageGeneratorClient()
        if not img_client.is_configured:
            logger.info("Image generator not configured, skipping image generation")
            return variants

        # Build engine-specific kwargs
        engine_kwargs: Dict[str, str] = {}
        if engine_model:
            if engine == "google":
                engine_kwargs["google_model"] = engine_model
            elif engine == "flux":
                engine_kwargs["flux_model"] = engine_model
            elif engine == "stability":
                engine_kwargs["stability_model"] = engine_model

        for variant in variants:
            content = variant.get("content", {})
            hero = content.get("hero", {})
            prompt = hero.get("hero_image_prompt", "")

            if not prompt:
                # Build a default prompt from context
                prompt = (
                    f"Professional {industry or 'service'} business photo: "
                    f"a licensed {service.lower()} expert performing work for a customer. "
                    f"Clean uniform, professional tools, well-lit workspace. "
                    f"Photorealistic, high quality, suitable for a landing page hero."
                )

            metadata = {
                "businessName": business_name,
                "businessType": industry or "service",
                "city": location.split(",")[0].strip() if location else "",
                "description": f"Professional {service} by {business_name}",
                "keywords": f"{service}, {industry}, {location}, professional",
            }

            try:
                result = await img_client.generate_single(
                    prompt=prompt,
                    engine=engine,
                    style="photorealistic",
                    size="1792x1024",  # Wide hero format
                    metadata=metadata,
                    **engine_kwargs,
                )
                if result.get("success") and result.get("image_url"):
                    hero["hero_image_url"] = result["image_url"]
                    logger.info("Hero image generated",
                                variant=variant.get("name"),
                                url=result["image_url"][:80])
                else:
                    logger.warning("Hero image generation failed",
                                   variant=variant.get("name"),
                                   error=result.get("error"))
            except Exception as e:
                logger.warning("Hero image generation exception",
                               variant=variant.get("name"), error=str(e))

            content["hero"] = hero
            variant["content"] = content

        return variants

    async def _call_ai(self, system: str, user_prompt: str, temperature: float = 0.6, max_tokens: int = 4000) -> Optional[Dict]:
        """Call Claude Opus with GPT-4o fallback for landing page generation."""
        result = await self.llm.call_json(
            system=system,
            user_msg=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            preferred_model=self.model,
        )
        if result is None:
            return None
        if result.get("fallback"):
            logger.info("Landing page generator used fallback model", model=result.get("model_used"))
        return result.get("data")

    async def _agent_strategist(self, ctx: Dict) -> Dict:
        """Agent 1: Determine offer angle, tone, CTA strategy, page structure."""
        system = """You are an elite Google Ads landing page strategist who has optimized 10,000+ pages
for local service businesses. You specialize in creating pages that score 10/10 on Google Ads
Quality Score by maximizing:

1. MESSAGE MATCH — Landing page headlines MUST echo the ad headlines and keywords that brought
   the visitor. If they searched "car locksmith near me", the H1 must contain those words.
2. RELEVANCE — Every section must reinforce the specific service searched for, not generic content.
3. ABOVE THE FOLD — Phone number, CTA button, headline, trust signals visible without scrolling.
4. MOBILE FIRST — 70%+ of clicks are mobile. Design for thumb-friendly CTAs, tap-to-call.
5. SPEED — Minimal content bloat. No unnecessary sections. Fast-loading structure.
6. TRUST — Real reviews, real credentials, real phone number. Google penalizes fake trust signals.
7. SINGLE GOAL — One conversion goal per page (call or form). No distractions, no navigation menus.

You determine the best offer angle, messaging tone, CTA strategy, and page structure.
Respond ONLY with valid JSON."""

        trust_block = "\n".join(f"  - {t}" for t in ctx.get('trust_signals', [])[:8]) or "  (none)"
        hours = ctx.get('constraints', {}).get('hours', 'N/A')
        is_emergency = ctx.get('constraints', {}).get('emergency', False)

        prompt = f"""Create a landing page strategy for this campaign:

SERVICE: {ctx['service']}
LOCATION: {ctx['location']}
INDUSTRY: {ctx['industry']}
BUSINESS: {ctx['business_name']}
PHONE: {ctx['phone']}
WEBSITE: {ctx.get('website', 'N/A')}
DESCRIPTION: {ctx.get('description', '') or 'N/A'}
HOURS: {hours}
EMERGENCY SERVICE: {'YES' if is_emergency else 'No'}
USPs: {json.dumps(ctx['usps'][:5])}
OFFERS: {json.dumps(ctx['offers'][:5])}
TRUST SIGNALS (real — use these, NOT generic placeholders):
{trust_block}
CAMPAIGN KEYWORDS: {json.dumps(ctx['campaign_keywords'][:10])}

Return JSON:
{{
  "offer_angle": "emergency" | "savings" | "expert" | "trust" | "speed",
  "primary_cta": "Call Now" | "Get Free Quote" | "Book Online" | "Schedule Today",
  "secondary_cta": "...",
  "tone": "urgent" | "professional" | "friendly" | "authoritative",
  "hero_approach": "problem-solution" | "offer-driven" | "social-proof" | "fear-of-loss",
  "page_sections": ["hero", "trust_bar", "services", "why_us", "reviews", "faq", "cta_footer"],
  "color_mood": "trust_blue" | "urgent_red" | "premium_dark" | "clean_white",
  "key_messages": ["msg1", "msg2", "msg3"],
  "seo": {{
    "title": "...",
    "meta_description": "...",
    "h1": "..."
  }},
  "style": {{
    "primary_color": "#hex",
    "accent_color": "#hex",
    "font_family": "Inter" | "Poppins" | "Montserrat"
  }},
  "conversion_hooks": ["urgency timer", "limited slots", "free estimate", "guaranteed price"],
  "rationale": "Brief explanation of strategy choices"
}}"""

        result = await self._call_ai(system, prompt, temperature=0.5)
        return result or {
            "offer_angle": "expert",
            "primary_cta": "Call Now",
            "tone": "professional",
            "page_sections": ["hero", "trust_bar", "services", "why_us", "reviews", "cta_footer"],
        }

    async def _agent_variant_generator(self, ctx: Dict, strategy: Dict) -> Optional[List[Dict]]:
        """Agent 2+3+4+5: Generate 3 complete landing page variants with copy, trust, and CRO."""
        system = """You are a team of Google Ads landing page experts: conversion copywriter,
trust enhancer, CRO specialist, and mobile UX designer.

You create landing pages specifically for GOOGLE ADS paid traffic — not organic SEO pages.
Every element is optimized for Quality Score and conversion rate.

GOOGLE ADS LANDING PAGE RULES:
1. HEADLINE = KEYWORD MATCH: The H1 must contain the exact keywords from the campaign.
   If keywords are ["car locksmith near me", "auto key replacement"], the headline must
   use those exact phrases. This is THE #1 factor for Quality Score.
2. NO NAVIGATION MENU: Google Ads landing pages should NOT have site navigation.
   The only links should be the CTA (call/form) and legal/privacy footer links.
3. PHONE NUMBER EVERYWHERE: Click-to-call button in hero, sticky header, and footer.
   Format: clickable tel: link. Must be the REAL business phone, never a placeholder.
4. SINGLE CONVERSION GOAL: Either phone call OR form submit. Not both competing.
   For emergency/local services, phone call is almost always better.
5. ABOVE THE FOLD MUST CONTAIN: headline with keyword, phone CTA, 1 trust signal, location.
6. SOCIAL PROOF WITH SPECIFICS: "4.9★ from 127 reviews" not "Great reviews".
   Use REAL trust signals provided — never fabricate credentials or ratings.
7. MOBILE-FIRST: Short paragraphs (2-3 sentences max), large tap targets, no horizontal scroll.
8. URGENCY WITHOUT BEING SPAMMY: "Available now" not "HURRY!!!". Professional urgency.
9. SERVICE AREA MENTION: Include the specific city/area in H1, subheadline, and throughout.
10. SCHEMA MARKUP HINTS: Include structured data suggestions for LocalBusiness.

Respond ONLY with valid JSON."""

        trust_block = "\n".join(f"  - {t}" for t in ctx.get('trust_signals', [])[:8]) or "  (none)"
        hours = ctx.get('constraints', {}).get('hours', 'N/A')
        is_emergency = ctx.get('constraints', {}).get('emergency', False)

        prompt = f"""Generate 3 landing page variants for this campaign.

── BUSINESS IDENTITY (use these REAL details — NOT placeholders) ──
BUSINESS: {ctx['business_name']}
PHONE: {ctx['phone']}
WEBSITE: {ctx.get('website', 'N/A')}
DESCRIPTION: {ctx.get('description', '') or 'N/A'}
INDUSTRY: {ctx.get('industry', '')}
HOURS: {hours}
EMERGENCY SERVICE: {'YES — this is an emergency/urgent service' if is_emergency else 'Standard'}

── TRUST SIGNALS (use EXACTLY these — do NOT invent fake ones) ──
{trust_block}

── CAMPAIGN CONTEXT ──
SERVICE: {ctx['service']}
LOCATION: {ctx['location']}
STRATEGY: {json.dumps(strategy)}
CAMPAIGN HEADLINES: {json.dumps(ctx['campaign_headlines'][:5])}
KEYWORDS: {json.dumps(ctx['campaign_keywords'][:10])}
USPs: {json.dumps(ctx['usps'][:5])}
OFFERS: {json.dumps(ctx['offers'][:3])}

Each variant must have a distinct angle:
- Variant A: EMERGENCY — urgency, speed, availability (24/7, fast response, emergency)
- Variant B: SAVINGS — deals, discounts, free estimates, price match
- Variant C: EXPERT — authority, experience, certifications, trust

For EACH variant, generate complete page content:

Return JSON:
{{
  "variants": [
    {{
      "name": "Emergency",
      "angle": "emergency",
      "content": {{
        "hero": {{
          "headline": "Attention-grabbing headline with business name (max 60 chars)",
          "subheadline": "Supporting line with location + trust signal (max 120 chars)",
          "cta_text": "Call Now — Free Estimate",
          "cta_phone": "{ctx['phone']}",
          "urgency_badge": "Available 24/7" or null,
          "hero_image_prompt": "Description for AI image generation"
        }},
        "trust_bar": {{
          "items": ["use REAL trust signals from above — e.g. actual years, actual rating, actual credentials"]
        }},
        "services_section": {{
          "heading": "Our {ctx['service']} Services",
          "services": [
            {{"name": "...", "description": "1-2 sentences", "icon": "key|shield|clock|star|wrench|phone"}},
            ...
          ]
        }},
        "why_us_section": {{
          "heading": "Why Choose {ctx['business_name']}",
          "reasons": [
            {{"title": "...", "description": "Use real trust signals, years, rating...", "icon": "..."}},
            ...
          ]
        }},
        "reviews_section": {{
          "heading": "What Our Customers Say",
          "reviews": [
            {{"name": "John D.", "rating": 5, "text": "Realistic review mentioning {ctx['service']}...", "service": "..."}},
            ...
          ]
        }},
        "faq_section": {{
          "heading": "Frequently Asked Questions",
          "faqs": [
            {{"question": "...", "answer": "..."}},
            ...
          ]
        }},
        "cta_footer": {{
          "heading": "Ready to Get Started?",
          "subtext": "...",
          "cta_text": "...",
          "cta_phone": "{ctx['phone']}"
        }}
      }}
    }},
    ... (2 more variants)
  ]
}}

CRITICAL GOOGLE ADS RULES:
- HEADLINE MUST MATCH KEYWORDS: The hero headline must contain the exact keywords from
  CAMPAIGN KEYWORDS above. If keyword is "car locksmith near me", headline must say
  "Car Locksmith Near Me" — this directly impacts Quality Score.
- Include "{ctx['business_name']}" in hero headlines and why_us headings
- Include "{ctx['location']}" in the hero headline or subheadline
- Use REAL trust signals from above in trust_bar items — NOT generic "Licensed & Insured" unless that IS the real signal
- Phone number {ctx['phone']} must appear as click-to-call CTA in hero, sticky bar, and footer (3+ times)
- NO navigation menu — this is a landing page, not a website. Only CTA buttons and footer links.
- CTA must be visible WITHOUT scrolling (above the fold)
- Reviews must feel authentic (varied names, specific details, mention the service)
- FAQ answers must be helpful and include keywords naturally
- why_us reasons should reference actual years of experience, rating, credentials from trust signals
- AD HEADLINE MATCH: If campaign headlines are provided above, echo their language in the page.
  Visitor sees ad headline → clicks → sees matching headline on page = high relevance = high Quality Score
- KEEP IT CONCISE: Google Ads visitors are high-intent. Don't bury the CTA under walls of text.
  Each section should be scannable in 3 seconds."""

        result = await self._call_ai(system, prompt, temperature=0.7, max_tokens=8192)
        if result and "variants" in result:
            return result["variants"]
        return None
