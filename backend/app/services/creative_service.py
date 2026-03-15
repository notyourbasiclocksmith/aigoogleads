"""
Creative Service — AI-powered ad copy generation and brand kit management.
Uses OpenAI to generate expert-quality Google Ads copy; falls back to
templates when the API key is not configured.
"""
import json
import structlog
from typing import Optional, Dict, Any, List
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.business_profile import BusinessProfile

logger = structlog.get_logger()


class CreativeService:
    def __init__(self, profile: Optional[BusinessProfile] = None, business_name: str = ""):
        self.profile = profile
        self.business_name = business_name

    async def generate_ad_copy(
        self,
        service: Optional[str] = None,
        location: Optional[str] = None,
        offer: Optional[str] = None,
        tone: Optional[str] = None,
        count: int = 10,
    ) -> Dict[str, Any]:
        svc = service or "Our Services"
        loc = location or ""
        brand = self.profile.brand_voice_json if self.profile else {}
        effective_tone = tone or brand.get("tone", "professional")

        # Try LLM-powered generation first
        llm_result = await self._generate_with_llm(svc, loc, offer, effective_tone, count)
        if llm_result:
            return {**llm_result, "tone_used": effective_tone, "service": svc, "location": loc, "generated_by": "openai"}

        # Fallback to templates
        headlines = self._gen_headlines(svc, loc, offer, effective_tone, count)
        descriptions = self._gen_descriptions(svc, loc, offer, effective_tone, min(count, 6))
        callouts = self._gen_callouts(svc, effective_tone, 8)
        sitelinks = self._gen_sitelinks(svc, 4)

        return {
            "headlines": headlines,
            "descriptions": descriptions,
            "callouts": callouts,
            "sitelinks": sitelinks,
            "tone_used": effective_tone,
            "service": svc,
            "location": loc,
            "generated_by": "template",
        }

    async def _generate_with_llm(
        self, service: str, location: str, offer: Optional[str],
        tone: str, count: int,
    ) -> Optional[Dict[str, Any]]:
        """Generate ad copy using OpenAI with expert Google Ads knowledge. Returns None on failure."""
        if not settings.OPENAI_API_KEY:
            return None

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Pull rich context from business profile
        biz_name = ""
        industry = "local service"
        phone = ""
        website = ""
        usps: List[str] = []
        services_list: List[str] = []
        trust_signals: List[str] = []
        if self.profile:
            biz_name = self.business_name or ""
            industry = (self.profile.industry_classification or "local service").lower()
            phone = self.profile.phone or ""
            website = self.profile.website_url or ""
            def _unwrap(raw) -> list:
                if isinstance(raw, list):
                    return raw
                if isinstance(raw, dict):
                    for k in ("list", "cities", "items"):
                        if isinstance(raw.get(k), list):
                            return raw[k]
                return []
            raw_usps = _unwrap(self.profile.usp_json)
            usps = [u if isinstance(u, str) else u.get("text", "") for u in raw_usps][:5]
            raw_svcs = _unwrap(self.profile.services_json)
            services_list = [s if isinstance(s, str) else s.get("name", "") for s in raw_svcs][:8]
            raw_trust = _unwrap(self.profile.trust_signals_json)
            trust_signals = [str(t) if isinstance(t, str) else t.get("text", str(t)) for t in raw_trust][:8]

        usp_block = "\n".join(f"  - {u}" for u in usps) if usps else "  (none provided)"
        svc_block = ", ".join(services_list) if services_list else service
        trust_block = "\n".join(f"  - {t}" for t in trust_signals) if trust_signals else "  (none provided)"

        is_emergency = industry in (
            "locksmith", "plumbing", "hvac", "towing", "restoration", "pest control",
            "roofing", "electrical", "garage door",
        )

        system_message = f"""You are a Google Ads Search specialist with 15+ years managing $100M+ in
search ad spend for local service businesses. You hold Google Ads Search and
Display certifications. You optimize simultaneously for:

1. QUALITY SCORE — Expected CTR, Ad Relevance, Landing Page Experience
2. AD STRENGTH — Google's RSA scoring system (target: Excellent)
3. CONVERSION RATE — psychological triggers that drive phone calls and form fills

You understand RSA combination math: 15 headlines × 4 descriptions = ~43,680
possible ad variations. Every asset you write must work INDEPENDENTLY and in
ANY combination with other assets.

CHARACTER LIMITS (strictly enforced by Google — even 1 char over = rejection):
- Headlines: ≤30 characters (including spaces and punctuation)
- Descriptions: ≤90 characters (including spaces and punctuation)
- Callouts: ≤25 characters
- Sitelink text: ≤25 characters

You respond ONLY with valid JSON."""

        prompt = f"""
╔═══════════════════════════════════════════════════════════╗
║  GOOGLE ADS CREATIVE GENERATION — EXPERT BRIEF            ║
╚═══════════════════════════════════════════════════════════╝

── CLIENT ──────────────────────────────────────────────────
Business:       {biz_name or '[Not set]'}
Industry:       {industry}
Target service: {service}
Location:       {location or 'local area'}
Website:        {website or 'N/A'}
Phone:          {phone or 'N/A'}
Brand tone:     {tone}
Other services: {svc_block}

USPs (real differentiators — USE these):
{usp_block}

Trust signals:
{trust_block}

{"Active offer: " + offer if offer else "No active promotion."}

── HEADLINES ({min(count, 15)} total, each ≤30 chars) ─────

Google requires DIVERSE headlines for "Excellent" Ad Strength.
Structure across these categories:

KEYWORD RELEVANCE (3 headlines):
  Must include "{service}" or close variant. These are your Position 1 pins.
  Boosts Quality Score "Ad Relevance" component directly.
  {'For ' + industry + ': include emergency/24-7 variants.' if is_emergency else ''}

GEO-TARGETING (2 headlines):
  Include "{location}" by name. Geo headlines get 15-25% higher CTR.
  Example: "{service} in {location}", "Serving {location} Area"

TRUST & SOCIAL PROOF (2-3 headlines):
  Specific numbers beat vague claims. "4.9★ on Google" > "Top Rated".
  License/insurance status, years in business, review count.

VALUE PROPOSITION (2 headlines):
  Convert USPs above into ≤30 char headlines. Be punchy and specific.
  "Flat-Rate Pricing" > "Great Prices". "90-Day Warranty" > "Quality Work".

CTA / OFFER (2 headlines):
  {"Include: " + offer[:30] if offer else "Strong CTAs: Free Estimate, Call Now, Book Online."}
  {'Emergency CTAs critical: "Call Now", "Open 24/7", "Fast Response"' if is_emergency else ''}

URGENCY / SCARCITY (2 headlines):
  {'CRITICAL for ' + industry + ': searchers are panicked/stressed.' if is_emergency else 'Time pressure where natural.'}
  "Available Right Now", "Same-Day Service", "30-Min Response"

BRAND (1 headline):
  Include "{biz_name}" if ≤30 chars.

── DESCRIPTIONS ({min(count, 6)} total, each ≤90 chars) ───

Each description must STAND ALONE (Google picks 2 to show).

D1 — PROBLEM → SOLUTION → CTA:
  Address the searcher's exact pain point for "{service}". Offer solution. End with CTA.

D2 — TRUST + DIFFERENTIATOR:
  Lead with proof (licensed, rated, insured). Follow with what makes you different.

D3 — OFFER/VALUE + URGENCY:
  {"Lead with: " + offer + ". " if offer else "Lead with value statement. "} Add urgency. Close with action.

D4 — LOCAL + REASSURANCE:
  Establish local authority. Reduce risk/anxiety. "Serving {location} for X years."

{f"D5 — EMERGENCY RESPONSE (for {industry}):" if is_emergency and min(count, 6) >= 5 else ""}
{f"  Fast response time, 24/7 availability, immediate dispatch." if is_emergency and min(count, 6) >= 5 else ""}

{f"D6 — COMPREHENSIVE SERVICE:" if min(count, 6) >= 6 else ""}
{f"  Mention range of services. Cross-sell opportunity." if min(count, 6) >= 6 else ""}

── CALLOUTS (8 total, each ≤25 chars) ─────────────────────
No periods. No CTAs. Pure trust & value signals.
Mix: licensing, guarantee, speed, pricing, availability, experience.
Example: "Licensed & Insured", "No Hidden Fees", "Same Day Service"

── SITELINKS (4 total) ────────────────────────────────────
Each: "text" (≤25 chars), "desc1" (≤35 chars), "desc2" (≤35 chars), "url"
Must cover: Services, Reviews/Testimonials, About/Why Us, Contact/Quote
URLs: use {website or 'https://example.com'} as base

── EXPERT RULES ────────────────────────────────────────────
1. COUNT EVERY CHARACTER. 1 over = rejected by Google.
2. Each headline UNIQUE in wording — repetition tanks Ad Strength.
3. BANNED phrases: "Best [X]", "#1 Provider", "Quality Work", "Great Service",
   vague superlatives without specific data to back them up.
4. ACTIVE VOICE + SECOND PERSON: "Get your", "Call us", "Book your".
5. Use {industry}-specific vocabulary matching real customer searches.
6. "{service}" must appear in ≥3 headlines for Ad Relevance scoring.
7. Every asset must answer: "Why THIS business, why NOW, why not competitors?"

── OUTPUT ──────────────────────────────────────────────────
{{
  "headlines": ["H1", "H2", ...],
  "descriptions": ["D1", "D2", ...],
  "callouts": ["C1", "C2", ...],
  "sitelinks": [{{"text": "...", "desc1": "...", "desc2": "...", "url": "..."}}],
  "pinning": {{
    "headline_pins": {{"1": 0, "2": 5}},
    "description_pins": {{"1": 0}}
  }},
  "rationale": "2-3 sentence strategic explanation"
}}

headline_pins: Position (1/2/3) → headline index (0-based).
description_pins: Position (1/2) → description index (0-based).
"""

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=2500,
            )
            content = response.choices[0].message.content
            if not content:
                return None

            data = json.loads(content)

            # Enforce character limits and clean up
            headlines = [h[:30] for h in data.get("headlines", []) if isinstance(h, str) and h.strip()]
            descriptions = [d[:90] for d in data.get("descriptions", []) if isinstance(d, str) and d.strip()]
            callouts = [c[:25] for c in data.get("callouts", []) if isinstance(c, str) and c.strip()]
            sitelinks = data.get("sitelinks", [])
            if not isinstance(sitelinks, list):
                sitelinks = []
            sitelinks = [s for s in sitelinks if isinstance(s, dict) and "text" in s][:4]

            pinning = data.get("pinning", {})
            rationale = data.get("rationale", "")

            if len(headlines) < 3:
                logger.warning("LLM returned too few headlines for creative service", count=len(headlines))
                return None

            logger.info(
                "Creative service expert LLM copy generated",
                headlines=len(headlines), descriptions=len(descriptions),
                callouts=len(callouts), sitelinks=len(sitelinks),
            )
            return {
                "headlines": headlines[:15],
                "descriptions": descriptions[:6],
                "callouts": callouts[:10],
                "sitelinks": sitelinks,
                "pinning": pinning,
                "rationale": rationale,
            }

        except Exception as e:
            logger.error("Creative service OpenAI call failed", error=str(e))
            return None

    # ── Template fallbacks ──────────────────────────────────────────────────

    def _gen_headlines(self, svc: str, loc: str, offer: Optional[str], tone: str, count: int) -> List[str]:
        base = [
            f"{svc} Experts",
            f"Professional {svc}",
            f"Top-Rated {svc}",
            f"Trusted {svc} Pros",
            f"Quality {svc} Service",
            f"{svc} You Can Trust",
            f"Licensed {svc} Team",
            f"Reliable {svc}",
            f"Award-Winning {svc}",
            f"Best {svc} Near You",
            f"Fast & Affordable {svc}",
            f"{svc} Done Right",
            f"Expert {svc} Help",
            f"Your {svc} Specialists",
            f"Guaranteed {svc}",
        ]
        if loc:
            base.extend([f"{svc} in {loc}", f"{loc} {svc} Pros", f"Serving {loc} Area"])
        if offer:
            base.append(offer[:30])
        if tone == "urgent":
            base.extend(["24/7 Emergency Service", "Call Now - Fast Response", "Same Day Available"])
        elif tone == "premium":
            base.extend(["Premium Quality Service", "Luxury Service Experience", "Excellence Guaranteed"])
        elif tone == "budget":
            base.extend(["Lowest Price Guarantee", "Budget-Friendly Rates", "Affordable Excellence"])

        return base[:count]

    def _gen_descriptions(self, svc: str, loc: str, offer: Optional[str], tone: str, count: int) -> List[str]:
        base = [
            f"Professional {svc.lower()} services delivered with expertise and care. Licensed, insured, and ready to help. Call today!",
            f"Looking for dependable {svc.lower()}? Our certified team provides top-quality work at fair prices. Free estimates available.",
            f"Trust the {svc.lower()} experts. Years of experience, thousands of satisfied customers. Satisfaction guaranteed every time.",
            f"Don't wait — get reliable {svc.lower()} from a team that cares. Quick response, quality work, competitive rates.",
            f"Experience the difference with our {svc.lower()} services. Fully licensed, insured, and committed to your satisfaction.",
            f"Need {svc.lower()} help? Our skilled professionals are standing by. Call now for a no-obligation consultation!",
        ]
        if loc:
            base.append(f"Proudly serving {loc} and surrounding communities. Contact us for expert {svc.lower()} today!")
        if offer:
            base.append(f"Special offer: {offer}. Professional {svc.lower()} at unbeatable value. Limited time — call now!")
        return base[:count]

    def _gen_callouts(self, svc: str, tone: str, count: int) -> List[str]:
        base = [
            "Licensed & Insured",
            "Free Estimates",
            "Satisfaction Guaranteed",
            "Experienced Professionals",
            "Locally Owned & Operated",
            "Fast Response Times",
            "Competitive Pricing",
            "Same Day Service",
            "5-Star Reviews",
            "No Hidden Fees",
        ]
        if tone == "urgent":
            base.extend(["24/7 Availability", "Emergency Service"])
        return base[:count]

    def _gen_sitelinks(self, svc: str, count: int) -> List[Dict[str, str]]:
        website = self.profile.website_url if self.profile else "https://example.com"
        return [
            {"text": "Our Services", "description": f"Full range of {svc.lower()} services", "url": f"{website}/services"},
            {"text": "Free Estimate", "description": "Get your no-obligation quote today", "url": f"{website}/contact"},
            {"text": "About Us", "description": "Meet our experienced team", "url": f"{website}/about"},
            {"text": "Testimonials", "description": "Read what customers are saying", "url": f"{website}/reviews"},
        ][:count]
