"""
Search Term Mining AI — Analyzes search terms from Google Ads accounts,
identifies opportunities (add as keyword) and waste (add as negative),
and generates AI-powered recommendations.

Designed to run after 7+ days of campaign data.
"""
import json
import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Optional, Any

from openai import AsyncOpenAI
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.search_term_performance import SearchTermPerformance
from app.models.keyword import Keyword
from app.models.negative import Negative
from app.models.campaign import Campaign
from app.models.ad_group import AdGroup

logger = structlog.get_logger()


class SearchTermMiner:
    """AI-powered search term analysis and recommendation engine."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def mine(
        self,
        google_customer_id: str,
        days: int = 30,
        min_impressions: int = 5,
    ) -> Dict[str, Any]:
        """
        Run full search term mining analysis.
        Returns structured recommendations: keywords to add, negatives to add,
        new ad group themes, and wasted spend analysis.
        """
        # 1. Fetch search term data
        since = date.today() - timedelta(days=days)
        search_terms = await self._get_search_terms(google_customer_id, since, min_impressions)

        if not search_terms:
            return {
                "status": "no_data",
                "message": f"No search terms found with {min_impressions}+ impressions in the last {days} days.",
                "recommendations": [],
            }

        # 2. Fetch existing keywords and negatives for context
        existing_keywords = await self._get_existing_keywords(google_customer_id)
        existing_negatives = await self._get_existing_negatives(google_customer_id)
        campaigns = await self._get_campaigns(google_customer_id)

        # 3. AI Analysis
        analysis = await self._analyze_with_ai(
            search_terms=search_terms,
            existing_keywords=existing_keywords,
            existing_negatives=existing_negatives,
            campaigns=campaigns,
        )

        if not analysis:
            # Fallback to rule-based if AI fails
            analysis = self._analyze_rule_based(
                search_terms, existing_keywords, existing_negatives
            )

        # 4. Structure the response
        return {
            "status": "complete",
            "analyzed_terms": len(search_terms),
            "date_range": {"start": since.isoformat(), "end": date.today().isoformat()},
            "summary": analysis.get("summary", ""),
            "total_spend_analyzed": sum(t["cost"] for t in search_terms),
            "wasted_spend": sum(
                t["cost"] for t in search_terms if t["conversions"] == 0
            ),
            "recommendations": analysis.get("recommendations", []),
            "add_as_keyword": analysis.get("add_as_keyword", []),
            "add_as_negative": analysis.get("add_as_negative", []),
            "new_ad_group_themes": analysis.get("new_ad_group_themes", []),
            "ai_generated": analysis.get("_ai_generated", False),
        }

    async def _get_search_terms(
        self, customer_id: str, since: date, min_impressions: int
    ) -> List[Dict]:
        result = await self.db.execute(
            select(
                SearchTermPerformance.search_term,
                SearchTermPerformance.campaign_id,
                SearchTermPerformance.ad_group_id,
                SearchTermPerformance.keyword_text,
                func.sum(SearchTermPerformance.impressions).label("impressions"),
                func.sum(SearchTermPerformance.clicks).label("clicks"),
                func.sum(SearchTermPerformance.cost_micros).label("cost_micros"),
                func.sum(SearchTermPerformance.conversions).label("conversions"),
                func.sum(SearchTermPerformance.conversion_value).label("conversion_value"),
            )
            .where(
                and_(
                    SearchTermPerformance.tenant_id == self.tenant_id,
                    SearchTermPerformance.google_customer_id == customer_id,
                    SearchTermPerformance.date >= since,
                )
            )
            .group_by(
                SearchTermPerformance.search_term,
                SearchTermPerformance.campaign_id,
                SearchTermPerformance.ad_group_id,
                SearchTermPerformance.keyword_text,
            )
            .having(func.sum(SearchTermPerformance.impressions) >= min_impressions)
            .order_by(func.sum(SearchTermPerformance.cost_micros).desc())
            .limit(500)
        )

        terms = []
        for row in result:
            cost = row.cost_micros / 1_000_000 if row.cost_micros else 0
            clicks = row.clicks or 0
            impressions = row.impressions or 0
            conversions = row.conversions or 0
            terms.append({
                "search_term": row.search_term,
                "campaign_id": row.campaign_id,
                "ad_group_id": row.ad_group_id,
                "matched_keyword": row.keyword_text or "",
                "impressions": impressions,
                "clicks": clicks,
                "cost": round(cost, 2),
                "conversions": round(conversions, 2),
                "conversion_value": round(row.conversion_value or 0, 2),
                "ctr": round(clicks / impressions, 4) if impressions > 0 else 0,
                "cpc": round(cost / clicks, 2) if clicks > 0 else 0,
                "cpa": round(cost / conversions, 2) if conversions > 0 else 0,
            })
        return terms

    async def _get_existing_keywords(self, customer_id: str) -> List[Dict]:
        result = await self.db.execute(
            select(Keyword.text, Keyword.match_type, Keyword.ad_group_id)
            .where(
                and_(
                    Keyword.tenant_id == self.tenant_id,
                    Keyword.status != "REMOVED",
                )
            )
            .limit(1000)
        )
        return [{"text": r.text, "match_type": r.match_type, "ad_group_id": r.ad_group_id} for r in result]

    async def _get_existing_negatives(self, customer_id: str) -> List[Dict]:
        result = await self.db.execute(
            select(Negative.keyword_text, Negative.match_type, Negative.level)
            .where(Negative.tenant_id == self.tenant_id)
            .limit(500)
        )
        return [{"text": r.keyword_text, "match_type": r.match_type, "level": r.level} for r in result]

    async def _get_campaigns(self, customer_id: str) -> List[Dict]:
        result = await self.db.execute(
            select(Campaign.google_campaign_id, Campaign.name, Campaign.type)
            .where(
                and_(
                    Campaign.tenant_id == self.tenant_id,
                    Campaign.status != "REMOVED",
                )
            )
        )
        return [{"id": r.google_campaign_id, "name": r.name, "type": r.type} for r in result]

    async def _analyze_with_ai(
        self,
        search_terms: List[Dict],
        existing_keywords: List[Dict],
        existing_negatives: List[Dict],
        campaigns: List[Dict],
    ) -> Optional[Dict]:
        if not settings.OPENAI_API_KEY:
            return None

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Prepare concise data for the AI
        top_spenders = sorted(search_terms, key=lambda t: t["cost"], reverse=True)[:50]
        top_converters = sorted(search_terms, key=lambda t: t["conversions"], reverse=True)[:30]
        wasters = [t for t in search_terms if t["conversions"] == 0 and t["cost"] > 2][:30]
        existing_kw_texts = list({k["text"].lower() for k in existing_keywords})[:100]
        existing_neg_texts = list({n["text"].lower() for n in existing_negatives})[:50]

        system = """You are a Google Ads search term optimization expert. You analyze search term reports
to find opportunities and eliminate waste. You respond ONLY with valid JSON."""

        prompt = f"""Analyze these search terms and generate actionable recommendations.

CAMPAIGNS: {json.dumps(campaigns[:10], default=str)}

TOP SPENDING SEARCH TERMS:
{json.dumps(top_spenders, default=str)}

TOP CONVERTING SEARCH TERMS:
{json.dumps(top_converters, default=str)}

WASTED SPEND (zero conversions, $2+ cost):
{json.dumps(wasters, default=str)}

EXISTING KEYWORDS (already in account): {json.dumps(existing_kw_texts[:50])}
EXISTING NEGATIVES: {json.dumps(existing_neg_texts[:30])}

Generate recommendations in these categories:

1. ADD AS KEYWORD — High-performing search terms not covered by exact match keywords.
   These drive conversions but aren't explicitly targeted.

2. ADD AS NEGATIVE — Search terms spending money with zero conversions.
   Include irrelevant queries, competitor terms being wasted on, etc.

3. NEW AD GROUP THEMES — Clusters of search terms that suggest a new ad group
   with its own targeted keywords and ad copy would perform better.

4. SUMMARY — Brief analysis of account health based on search terms.

Return JSON:
{{
  "summary": "2-3 sentence analysis of search term health and biggest opportunities",
  "add_as_keyword": [
    {{"search_term": "...", "recommended_match_type": "EXACT"|"PHRASE", "reason": "...", "campaign_id": "...", "ad_group_id": "...", "conversions": N, "cpa": N, "priority": "high"|"medium"|"low"}},
    ...
  ],
  "add_as_negative": [
    {{"search_term": "...", "recommended_match_type": "EXACT"|"PHRASE", "reason": "...", "campaign_id": "...", "cost_wasted": N, "clicks": N, "priority": "high"|"medium"|"low"}},
    ...
  ],
  "new_ad_group_themes": [
    {{"theme": "theme name", "keywords": ["kw1", "kw2", ...], "reason": "...", "estimated_search_terms": N}},
    ...
  ],
  "recommendations": [
    {{"type": "add_keyword"|"add_negative"|"new_ad_group"|"bid_adjustment"|"pause_keyword", "action": "...", "reason": "...", "impact": "high"|"medium"|"low", "entity": "..."}}
  ]
}}"""

        try:
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=3000,
            )
            content = resp.choices[0].message.content
            if content:
                result = json.loads(content)
                result["_ai_generated"] = True
                return result
        except Exception as e:
            logger.error("Search term mining AI failed", error=str(e))

        return None

    def _analyze_rule_based(
        self,
        search_terms: List[Dict],
        existing_keywords: List[Dict],
        existing_negatives: List[Dict],
    ) -> Dict:
        """Rule-based fallback when AI is unavailable."""
        existing_kw_set = {k["text"].lower() for k in existing_keywords}
        existing_neg_set = {n["text"].lower() for n in existing_negatives}

        add_as_keyword = []
        add_as_negative = []

        for t in search_terms:
            st = t["search_term"].lower()
            if st in existing_kw_set or st in existing_neg_set:
                continue

            if t["conversions"] >= 1 and st not in existing_kw_set:
                add_as_keyword.append({
                    "search_term": t["search_term"],
                    "recommended_match_type": "EXACT",
                    "reason": f"{t['conversions']} conversions at ${t['cpa']} CPA",
                    "campaign_id": t["campaign_id"],
                    "ad_group_id": t["ad_group_id"],
                    "conversions": t["conversions"],
                    "cpa": t["cpa"],
                    "priority": "high" if t["conversions"] >= 3 else "medium",
                })
            elif t["conversions"] == 0 and t["cost"] > 5:
                add_as_negative.append({
                    "search_term": t["search_term"],
                    "recommended_match_type": "EXACT",
                    "reason": f"${t['cost']} spent, 0 conversions",
                    "campaign_id": t["campaign_id"],
                    "cost_wasted": t["cost"],
                    "clicks": t["clicks"],
                    "priority": "high" if t["cost"] > 20 else "medium",
                })

        total_waste = sum(t["cost"] for t in search_terms if t["conversions"] == 0)
        total_spend = sum(t["cost"] for t in search_terms)

        return {
            "summary": f"Analyzed {len(search_terms)} search terms. ${total_waste:.0f} wasted on non-converting terms ({(total_waste/total_spend*100):.0f}% of spend)." if total_spend > 0 else "No spend data available.",
            "add_as_keyword": sorted(add_as_keyword, key=lambda x: x.get("conversions", 0), reverse=True)[:20],
            "add_as_negative": sorted(add_as_negative, key=lambda x: x.get("cost_wasted", 0), reverse=True)[:20],
            "new_ad_group_themes": [],
            "recommendations": [],
            "_ai_generated": False,
        }
