"""
Landing Page Generator — AI agent pipeline that creates high-converting
landing pages with 3 variants (Emergency, Savings, Expert).

Pipeline agents:
  1. Landing Page Strategist — offer angle, tone, CTA strategy
  2. Conversion Copywriter — headlines, body, CTAs
  3. Trust Enhancer — reviews, badges, guarantees
  4. CRO Auditor — conversion optimization pass
  5. Variant Generator — 3 distinct variants
"""
import json
import uuid
import time
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.landing_page import LandingPage, LandingPageVariant

logger = structlog.get_logger()


class LandingPageGenerator:
    """AI-powered landing page generation with multi-agent pipeline."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

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
    ) -> Dict[str, Any]:
        """
        Full pipeline: strategy → copy → trust → CRO audit → 3 variants → save.
        Returns the LandingPage record with variants.
        """
        if not self.client:
            return {"error": "AI not configured (no API key)"}

        usps = usps or []
        offers = offers or []
        campaign_keywords = campaign_keywords or []
        campaign_headlines = campaign_headlines or []
        trust_signals = trust_signals or []
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

        # Save to DB
        slug = f"{service.lower().replace(' ', '-')}-{location.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
        slug = slug.replace("--", "-").strip("-")[:250]

        lp = LandingPage(
            tenant_id=self.tenant_id,
            name=f"{service} — {location}" if location else service,
            slug=slug,
            service=service,
            location=location,
            status="draft",
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
                }
                for vr in variant_records
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
        if not self.client:
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

        result = await self._call_ai(system, prompt, temperature=0.4, max_tokens=16000)
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
        slug = f"{(new_service or source_lp.service or 'page').lower().replace(' ', '-')}-{(new_location or source_lp.location or 'local').lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
        slug = slug.replace("--", "-").strip("-")[:250]

        new_lp = LandingPage(
            tenant_id=self.tenant_id,
            name=f"{new_service or source_lp.service} — {new_location or source_lp.location}" if (new_location or source_lp.location) else (new_service or source_lp.service or source_lp.name),
            slug=slug,
            service=new_service or source_lp.service,
            location=new_location or source_lp.location,
            status="draft",
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

    async def _call_ai(self, system: str, user_prompt: str, temperature: float = 0.6, max_tokens: int = 4000) -> Optional[Dict]:
        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if content:
                return json.loads(content)
        except Exception as e:
            logger.error("Landing page AI call failed", error=str(e))
        return None

    async def _agent_strategist(self, ctx: Dict) -> Dict:
        """Agent 1: Determine offer angle, tone, CTA strategy, page structure."""
        system = """You are an elite landing page strategist who has optimized 10,000+ pages
for local service businesses. You determine the best offer angle, messaging tone,
CTA strategy, and page structure for maximum conversions. Respond ONLY with valid JSON."""

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
        system = """You are a team of landing page experts: conversion copywriter, trust enhancer,
CRO specialist, and mobile UX designer. You create complete, high-converting landing page
content ready for production. Every element is optimized for conversions.
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

CRITICAL RULES:
- Include "{ctx['business_name']}" in hero headlines and why_us headings
- Use REAL trust signals from above in trust_bar items — NOT generic "Licensed & Insured" unless that IS the real signal
- Phone number {ctx['phone']} must appear 3+ times per page
- Every headline must include the service name and location
- CTA must be visible without scrolling
- Reviews must feel authentic (varied names, specific details, mention the service)
- FAQ answers must be helpful and include keywords naturally
- why_us reasons should reference actual years of experience, rating, credentials from trust signals"""

        result = await self._call_ai(system, prompt, temperature=0.7)
        if result and "variants" in result:
            return result["variants"]
        return None
