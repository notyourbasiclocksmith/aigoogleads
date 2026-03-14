"""
Campaign Auditor — Post-generation AI quality audit that checks:
  - Duplicate keywords across ad groups
  - Overlap with existing campaigns
  - Missing negative keywords
  - Weak ad copy
  - Missing extensions
  - Keyword-to-ad message match
  - Budget/bidding issues
"""
import json
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.campaign import Campaign
from app.models.keyword import Keyword

logger = structlog.get_logger()


class CampaignAuditor:
    """AI-powered post-generation campaign quality audit."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def audit_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        """Audit a campaign draft before launch."""
        if not self.client:
            return self._rule_based_audit(draft)

        # Gather existing campaigns for overlap check
        existing = await self._get_existing_campaigns()

        return await self._ai_audit(draft, existing)

    async def _get_existing_campaigns(self) -> List[Dict]:
        result = await self.db.execute(
            select(Campaign.name, Campaign.status, Campaign.settings_json)
            .where(
                and_(
                    Campaign.tenant_id == self.tenant_id,
                    Campaign.status != "REMOVED",
                )
            )
            .limit(50)
        )
        return [{"name": r.name, "status": r.status} for r in result]

    async def _ai_audit(self, draft: Dict, existing: List[Dict]) -> Dict[str, Any]:
        system = """You are a Google Ads account auditor with 15+ years experience.
You catch quality issues that waste budget and hurt Quality Score.
You are thorough, specific, and action-oriented. Respond ONLY with valid JSON."""

        # Extract draft components
        campaign = draft.get("campaign", {})
        ad_groups = draft.get("ad_groups", [])
        all_keywords = []
        all_ads = []
        for ag in ad_groups:
            for kw in ag.get("keywords", []):
                kw_text = kw.get("text", kw) if isinstance(kw, dict) else kw
                all_keywords.append({"text": kw_text, "ad_group": ag.get("name", "")})
            for ad in ag.get("ads", []):
                all_ads.append({"headlines": ad.get("headlines", []), "descriptions": ad.get("descriptions", []), "ad_group": ag.get("name", "")})

        prompt = f"""Audit this Google Ads campaign draft for quality issues.

CAMPAIGN: {json.dumps(campaign, default=str)[:1000]}

AD GROUPS ({len(ad_groups)}):
{json.dumps([{"name": ag.get("name"), "keyword_count": len(ag.get("keywords", []))} for ag in ad_groups], default=str)}

ALL KEYWORDS ({len(all_keywords)}):
{json.dumps(all_keywords[:60], default=str)}

ALL ADS ({len(all_ads)}):
{json.dumps(all_ads[:10], default=str)}

EXISTING CAMPAIGNS IN ACCOUNT:
{json.dumps(existing[:20], default=str)}

EXTENSIONS: {json.dumps(draft.get("extensions", {}), default=str)[:500]}

Check for these issues:

1. DUPLICATE KEYWORDS — same keyword text in multiple ad groups
2. CAMPAIGN OVERLAP — new campaign targets same services as existing ones
3. MISSING NEGATIVES — obvious negative keywords not included
4. WEAK AD COPY — headlines too generic, no CTA, no USP, character limit issues
5. MISSING EXTENSIONS — sitelinks, callouts, structured snippets, call extension
6. MESSAGE MISMATCH — keywords don't match ad copy themes
7. STRUCTURE ISSUES — too many/few keywords per ad group, poor grouping
8. BUDGET/BID CONCERNS — if budget data available

Return JSON:
{{
  "overall_score": 0-100,
  "grade": "A+" | "A" | "B+" | "B" | "C" | "D" | "F",
  "issues": [
    {{
      "category": "duplicate_keywords" | "campaign_overlap" | "missing_negatives" | "weak_ad_copy" | "missing_extensions" | "message_mismatch" | "structure" | "budget",
      "severity": "critical" | "warning" | "info",
      "title": "Short description",
      "details": "Specific explanation with examples",
      "fix": "How to resolve this"
    }},
    ...
  ],
  "strengths": ["Good keyword grouping", "Strong CTAs", ...],
  "summary": "2-3 sentence overall assessment",
  "estimated_quality_score": "7-9/10",
  "recommendations": [
    "Top priority action 1",
    "Top priority action 2",
    "Top priority action 3"
  ]
}}"""

        try:
            resp = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2500,
            )
            content = resp.choices[0].message.content
            if content:
                result = json.loads(content)
                result["_ai_generated"] = True
                return result
        except Exception as e:
            logger.error("Campaign audit AI failed", error=str(e))

        return self._rule_based_audit(draft)

    def _rule_based_audit(self, draft: Dict) -> Dict[str, Any]:
        """Fallback rule-based audit when AI is unavailable."""
        issues = []
        ad_groups = draft.get("ad_groups", [])

        # Check duplicate keywords
        all_kw_texts = {}
        for ag in ad_groups:
            for kw in ag.get("keywords", []):
                text = (kw.get("text", kw) if isinstance(kw, dict) else kw).lower()
                if text in all_kw_texts:
                    issues.append({
                        "category": "duplicate_keywords",
                        "severity": "warning",
                        "title": f"Duplicate keyword: {text}",
                        "details": f"Found in '{all_kw_texts[text]}' and '{ag.get('name', '')}'",
                        "fix": "Remove from one ad group or use negatives to prevent overlap",
                    })
                else:
                    all_kw_texts[text] = ag.get("name", "")

        # Check ad group sizes
        for ag in ad_groups:
            kw_count = len(ag.get("keywords", []))
            if kw_count > 25:
                issues.append({
                    "category": "structure",
                    "severity": "warning",
                    "title": f"Too many keywords in '{ag.get('name', '')}'",
                    "details": f"{kw_count} keywords — consider splitting into tighter groups",
                    "fix": "Split into 2-3 ad groups with 10-15 keywords each",
                })

        # Check extensions
        extensions = draft.get("extensions", {})
        if not extensions.get("sitelinks"):
            issues.append({
                "category": "missing_extensions",
                "severity": "warning",
                "title": "Missing sitelink extensions",
                "details": "Sitelinks improve CTR by 10-15%",
                "fix": "Add 4-6 sitelinks",
            })

        score = max(0, 100 - len(issues) * 10)
        return {
            "overall_score": score,
            "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D",
            "issues": issues,
            "strengths": [],
            "summary": f"Found {len(issues)} issues in campaign draft.",
            "recommendations": [i["fix"] for i in issues[:3]],
            "_ai_generated": False,
        }
