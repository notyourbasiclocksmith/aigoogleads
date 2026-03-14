"""
Expansion Scorer — AI agent that identifies and scores expansion opportunities
from a source campaign. Ranks by relevance, commercial intent, keyword demand,
similarity to winning campaign, and competition risk.

Supports:
  - Make/brand expansion (Ford → BMW, Toyota, Honda...)
  - Service expansion (key replacement → ignition repair, key programming...)
  - Location expansion
"""
import json
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.campaign import Campaign
from app.models.landing_page import ExpansionRecommendation

logger = structlog.get_logger()


class ExpansionScorer:
    """AI-powered expansion opportunity scoring engine."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def score_expansions(
        self,
        source_campaign_name: str,
        service: str,
        location: str = "",
        industry: str = "",
        existing_campaign_names: List[str] = None,
        source_campaign_id: str = None,
    ) -> Dict[str, Any]:
        """
        Generate and score expansion ideas from a source campaign.
        Returns ranked list with scores 0-100.
        """
        if not self.client:
            return {"expansions": [], "error": "AI not configured"}

        existing_campaign_names = existing_campaign_names or []

        # Get existing campaigns to avoid duplicates
        if not existing_campaign_names:
            result = await self.db.execute(
                select(Campaign.name)
                .where(and_(Campaign.tenant_id == self.tenant_id, Campaign.status != "REMOVED"))
                .limit(100)
            )
            existing_campaign_names = [r.name for r in result]

        analysis = await self._ai_score(
            source_campaign_name=source_campaign_name,
            service=service,
            location=location,
            industry=industry,
            existing=existing_campaign_names,
        )

        if not analysis:
            return {"expansions": [], "error": "AI scoring failed"}

        # Save expansion recommendations to DB
        expansions = analysis.get("expansions", [])
        for exp in expansions:
            rec = ExpansionRecommendation(
                tenant_id=self.tenant_id,
                source_campaign_id=source_campaign_id,
                expansion_type=exp.get("type", "make_expansion"),
                service_name=exp.get("service_name", ""),
                score=exp.get("score", 0),
                scoring_json={
                    "relevance": exp.get("relevance_score", 0),
                    "commercial_intent": exp.get("intent_score", 0),
                    "keyword_demand": exp.get("demand_score", 0),
                    "competition_risk": exp.get("competition_score", 0),
                    "similarity": exp.get("similarity_score", 0),
                },
                campaign_prompt=exp.get("campaign_prompt", ""),
                status="suggested",
            )
            self.db.add(rec)

        await self.db.commit()

        return {
            "source_campaign": source_campaign_name,
            "total_expansions": len(expansions),
            "expansions": expansions,
            "make_expansions": [e for e in expansions if e.get("type") == "make_expansion"],
            "service_expansions": [e for e in expansions if e.get("type") == "service_expansion"],
            "summary": analysis.get("summary", ""),
        }

    async def _ai_score(
        self,
        source_campaign_name: str,
        service: str,
        location: str,
        industry: str,
        existing: List[str],
    ) -> Optional[Dict]:
        system = """You are a Google Ads growth strategist who identifies expansion opportunities
for local service businesses. You score each opportunity on multiple dimensions and
produce ready-to-use campaign prompts. Respond ONLY with valid JSON."""

        prompt = f"""Analyze this campaign and generate scored expansion opportunities.

SOURCE CAMPAIGN: {source_campaign_name}
SERVICE: {service}
LOCATION: {location}
INDUSTRY: {industry}
EXISTING CAMPAIGNS (avoid duplicates): {json.dumps(existing[:30])}

Generate expansion ideas in two categories:

1. MAKE/BRAND EXPANSIONS — If the service involves a specific brand/make, suggest all
   related makes. E.g., "Ford key replacement" → Toyota, Honda, BMW, Mercedes, etc.
   Include at least 10-15 make expansions if applicable.

2. SERVICE EXPANSIONS — Related services the business likely also provides.
   E.g., "car key replacement" → key programming, ignition repair, lockout service, etc.
   Include 5-10 service expansions.

Score each 0-100 across 5 dimensions:
- relevance_score: How related to the source campaign
- intent_score: Commercial/buying intent of searchers
- demand_score: Estimated search volume/keyword demand
- competition_score: Lower competition = higher score (inverted)
- similarity_score: How similar the campaign structure would be (easy to replicate)

Final score = weighted average: relevance(25%) + intent(25%) + demand(20%) + competition(15%) + similarity(15%)

Return JSON:
{{
  "expansions": [
    {{
      "service_name": "Toyota Key Replacement",
      "type": "make_expansion" | "service_expansion",
      "score": 96,
      "relevance_score": 98,
      "intent_score": 95,
      "demand_score": 94,
      "competition_score": 92,
      "similarity_score": 99,
      "estimated_monthly_searches": 500,
      "campaign_prompt": "Create a Google Ads campaign for Toyota car key replacement and key programming in {location}. Target emergency and scheduled customers. Include key fob replacement, transponder key programming, and lost key replacement keywords.",
      "suggested_keywords": ["toyota key replacement", "toyota key fob", ...],
      "rationale": "Toyota is the #1 selling brand, high demand, same equipment needed"
    }},
    ...
  ],
  "summary": "Brief strategy explanation — why these expansions and in what order",
  "estimated_total_monthly_searches": N,
  "revenue_potential": "Brief estimate of additional revenue from all expansions"
}}

Sort by score descending. Skip any that duplicate existing campaigns."""

        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=4000,
            )
            content = resp.choices[0].message.content
            if content:
                return json.loads(content)
        except Exception as e:
            logger.error("Expansion scoring AI failed", error=str(e))

        return None
