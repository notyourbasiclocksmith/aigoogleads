"""
Auto-expand specialty services — AI detects that a business specializing in
one niche (e.g., Jaguar KVM Repair) could serve adjacent niches
(BMW, Mercedes, Audi, Land Rover, etc.) and generates expansion suggestions
with ready-to-use campaign prompts.
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


class ServiceExpander:
    """AI-powered service expansion suggestion engine."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def suggest_expansions(self) -> Dict[str, Any]:
        """
        Analyze current business profile and campaigns to suggest
        related services/niches the business could expand into.
        """
        # 1. Load business profile
        result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return {"status": "error", "message": "No business profile found."}

        # 2. Load existing campaigns
        camp_result = await self.db.execute(
            select(Campaign.name, Campaign.type, Campaign.status)
            .where(Campaign.tenant_id == self.tenant_id)
            .limit(50)
        )
        campaigns = [{"name": r.name, "type": r.type, "status": r.status} for r in camp_result]

        # 3. Extract profile data
        services = profile.services_json if isinstance(profile.services_json, list) else []
        svc_names = [s if isinstance(s, str) else s.get("name", "") for s in services]
        industry = (profile.industry_classification or "service").lower()
        locations = profile.locations_json if isinstance(profile.locations_json, list) else []
        loc_names = [l if isinstance(l, str) else l.get("name", "") for l in locations]
        usps = profile.usp_json if isinstance(profile.usp_json, list) else []
        usp_texts = [u if isinstance(u, str) else u.get("text", "") for u in usps]
        website = profile.website_url or ""

        # 4. AI expansion analysis
        expansions = await self._expand_with_ai(
            industry=industry,
            services=svc_names,
            locations=loc_names,
            usps=usp_texts,
            website=website,
            existing_campaigns=[c["name"] for c in campaigns],
        )

        if not expansions:
            return {
                "status": "no_suggestions",
                "message": "Could not generate expansion suggestions.",
                "suggestions": [],
            }

        return {
            "status": "complete",
            "current_services": svc_names,
            "industry": industry,
            "suggestions": expansions.get("suggestions", []),
            "estimated_total_campaigns": expansions.get("estimated_total_campaigns", 0),
            "rationale": expansions.get("rationale", ""),
            "ai_generated": True,
        }

    async def _expand_with_ai(
        self,
        industry: str,
        services: List[str],
        locations: List[str],
        usps: List[str],
        website: str,
        existing_campaigns: List[str],
    ) -> Optional[Dict]:
        if not settings.OPENAI_API_KEY:
            return None

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        system = """You are a business growth strategist specializing in local service businesses
and Google Ads expansion. You identify adjacent niches and services that a business
can expand into based on their existing expertise. You respond ONLY with valid JSON."""

        prompt = f"""Analyze this business and suggest expansion opportunities.

INDUSTRY: {industry}
CURRENT SERVICES: {json.dumps(services)}
LOCATIONS: {json.dumps(locations[:5])}
USPs: {json.dumps(usps[:5])}
WEBSITE: {website}
EXISTING CAMPAIGNS: {json.dumps(existing_campaigns[:20])}

Identify adjacent services, makes, models, or niches this business could expand into.

Examples of expansion patterns:
- "Jaguar KVM Repair" → BMW, Mercedes, Audi, Land Rover, Porsche key/module services
- "Residential Locksmith" → Commercial, Automotive, Safe, Emergency
- "AC Repair" → Heating, Ductwork, Indoor Air Quality, Smart Thermostat
- "iPhone Screen Repair" → Samsung, iPad, MacBook, Game Console repair

For each suggestion:
1. Name the expanded service
2. Explain why it's a good fit (skill transfer, equipment overlap, market demand)
3. Provide a ready-to-use campaign prompt that would generate a full Google Ads campaign
4. Estimate monthly search volume potential (low/medium/high)
5. Rate difficulty of entry (easy/moderate/hard)

Return JSON:
{{
  "suggestions": [
    {{
      "service_name": "BMW Key Programming",
      "category": "vehicle_make_expansion" | "service_type_expansion" | "market_segment_expansion",
      "why_good_fit": "Same diagnostic equipment and key programming skills as Jaguar...",
      "search_volume": "high" | "medium" | "low",
      "entry_difficulty": "easy" | "moderate" | "hard",
      "estimated_monthly_searches": 500,
      "campaign_prompt": "Create a Google Ads campaign for BMW key programming and BCM repair services...",
      "suggested_keywords": ["bmw key programming", "bmw key fob replacement", ...],
      "priority": 1
    }},
    ...
  ],
  "estimated_total_campaigns": N,
  "rationale": "Brief explanation of the expansion strategy and why these niches were chosen"
}}

Generate 5-15 expansion suggestions ordered by priority (best opportunity first).
Skip any services that already have campaigns."""

        try:
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.6,
                max_tokens=3000,
            )
            content = resp.choices[0].message.content
            if content:
                return json.loads(content)
        except Exception as e:
            logger.error("Service expansion AI failed", error=str(e))

        return None
