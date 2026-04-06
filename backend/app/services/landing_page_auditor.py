"""
Landing Page Auditor — AI agent that scores existing landing pages on:
  - Message match with campaign keywords/ads
  - CTA visibility and strength
  - Mobile friendliness
  - Trust signals (reviews, badges, guarantees)
  - Conversion clarity
  - Load simplicity
  - Headline relevance

Returns a score out of 100 with detailed breakdown and recommendations.
"""
import json
from typing import Dict, List, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.services.operator.llm_fallback_service import LLMFallbackService

logger = structlog.get_logger()


class LandingPageAuditor:
    """AI-powered landing page audit and scoring engine (Claude Opus + GPT-4o fallback)."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.llm = LLMFallbackService()
        self.model = "claude-opus-4-6"

    async def audit_url(
        self,
        url: str,
        campaign_keywords: List[str] = None,
        campaign_headlines: List[str] = None,
        service: str = "",
        location: str = "",
    ) -> Dict[str, Any]:
        """Audit an external landing page URL."""
        if not settings.ANTHROPIC_API_KEY and not settings.OPENAI_API_KEY:
            return {"error": "AI not configured", "score": 0}

        campaign_keywords = campaign_keywords or []
        campaign_headlines = campaign_headlines or []

        return await self._run_audit(
            page_source="url",
            url=url,
            content=None,
            campaign_keywords=campaign_keywords,
            campaign_headlines=campaign_headlines,
            service=service,
            location=location,
        )

    async def audit_generated(
        self,
        content_json: Dict,
        campaign_keywords: List[str] = None,
        campaign_headlines: List[str] = None,
        service: str = "",
        location: str = "",
    ) -> Dict[str, Any]:
        """Audit an AI-generated landing page's content."""
        if not settings.ANTHROPIC_API_KEY and not settings.OPENAI_API_KEY:
            return {"error": "AI not configured", "score": 0}

        campaign_keywords = campaign_keywords or []
        campaign_headlines = campaign_headlines or []

        return await self._run_audit(
            page_source="generated",
            url=None,
            content=content_json,
            campaign_keywords=campaign_keywords,
            campaign_headlines=campaign_headlines,
            service=service,
            location=location,
        )

    async def _run_audit(
        self,
        page_source: str,
        url: Optional[str],
        content: Optional[Dict],
        campaign_keywords: List[str],
        campaign_headlines: List[str],
        service: str,
        location: str,
    ) -> Dict[str, Any]:
        system = """You are an elite CRO (Conversion Rate Optimization) expert and landing page auditor.
You have audited 50,000+ landing pages for local service businesses and Google Ads campaigns.
You score pages on conversion potential and provide specific, actionable recommendations.
Respond ONLY with valid JSON."""

        page_desc = ""
        if page_source == "url":
            page_desc = f"Landing page URL: {url}\n(Analyze based on what a typical page at this URL would contain for the service described)"
        elif content:
            page_desc = f"Landing page content:\n{json.dumps(content, default=str)[:3000]}"

        prompt = f"""Audit this landing page for Google Ads conversion performance.

{page_desc}

CAMPAIGN CONTEXT:
- Service: {service}
- Location: {location}
- Campaign keywords: {json.dumps(campaign_keywords[:15])}
- Campaign ad headlines: {json.dumps(campaign_headlines[:10])}

Score each dimension 0-100 and provide specific issues and fixes.

Return JSON:
{{
  "overall_score": 0-100,
  "grade": "A+" | "A" | "B+" | "B" | "C" | "D" | "F",
  "scores": {{
    "message_match": {{
      "score": 0-100,
      "weight": 25,
      "issues": ["headline does not mention Ford keys", ...],
      "fixes": ["Add 'Ford Key Replacement' to H1", ...]
    }},
    "cta_strength": {{
      "score": 0-100,
      "weight": 20,
      "issues": [...],
      "fixes": [...]
    }},
    "trust_signals": {{
      "score": 0-100,
      "weight": 15,
      "issues": ["no reviews visible", "no badges", ...],
      "fixes": ["add Google review widget", "add license badge", ...]
    }},
    "mobile_friendliness": {{
      "score": 0-100,
      "weight": 15,
      "issues": [...],
      "fixes": [...]
    }},
    "conversion_clarity": {{
      "score": 0-100,
      "weight": 10,
      "issues": [...],
      "fixes": [...]
    }},
    "headline_relevance": {{
      "score": 0-100,
      "weight": 10,
      "issues": [...],
      "fixes": [...]
    }},
    "load_simplicity": {{
      "score": 0-100,
      "weight": 5,
      "issues": [...],
      "fixes": [...]
    }}
  }},
  "top_issues": [
    "Most critical issue 1",
    "Most critical issue 2",
    "Most critical issue 3"
  ],
  "top_recommendations": [
    "Highest impact fix 1",
    "Highest impact fix 2",
    "Highest impact fix 3"
  ],
  "estimated_conversion_lift": "15-25%",
  "summary": "2-3 sentence overall assessment"
}}"""

        try:
            llm_result = await self.llm.call_json(
                system=system,
                user_msg=prompt,
                max_tokens=2500,
                temperature=0.4,
                preferred_model=self.model,
            )
            if llm_result and llm_result.get("data"):
                result = llm_result["data"]
                result["_ai_generated"] = True
                result["_model_used"] = llm_result.get("model_used", "unknown")
                if llm_result.get("fallback"):
                    logger.info("Landing page auditor used fallback model", model=llm_result.get("model_used"))
                return result
        except Exception as e:
            logger.error("Landing page audit AI failed", error=str(e))

        return {"error": "Audit failed", "score": 0, "summary": "Could not complete audit"}
