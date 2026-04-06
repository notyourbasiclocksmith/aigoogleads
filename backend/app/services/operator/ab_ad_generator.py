"""
A/B Ad Variation Generator
===========================

Uses Claude Opus to generate new ad variations based on:
1. Current ad performance data (CTR, conversions, CPC)
2. Winning headlines/descriptions (keep what works)
3. New angles: urgency, premium positioning, price anchoring, social proof
4. Competitor ad copy gaps

Generates 5 new headline variations + 3 new angle variants per ad group,
then lets the user approve before deploying as new RSA experiments.
"""

import json
import time
import uuid
import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.operator import OperatorMessage
from app.models.pipeline_execution_log import PipelineExecutionLog

logger = structlog.get_logger()


class ABAdGenerator:
    """Generates A/B ad copy variations using Claude Opus + performance data."""

    def __init__(self, db: AsyncSession, tenant_id: str, ads_client: Any):
        self.db = db
        self.tenant_id = tenant_id
        self.ads_client = ads_client
        self.claude = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-opus-4-6"  # Ad copy quality = CTR = $$

    async def generate_variations(
        self,
        campaign_id: str,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate A/B ad variations for all ad groups in a campaign.

        Returns:
        {
            "campaign_id": "...",
            "ad_groups": [
                {
                    "ad_group_id": "...",
                    "ad_group_name": "...",
                    "current_performance": {...},
                    "winning_elements": [...],
                    "new_headlines": [...],
                    "new_descriptions": [...],
                    "angles": [
                        {"name": "urgency", "headlines": [...], "descriptions": [...]},
                        {"name": "premium", "headlines": [...], "descriptions": [...]},
                        {"name": "price", "headlines": [...], "descriptions": [...]},
                    ]
                }
            ],
            "summary": "..."
        }
        """
        # ── Fetch current ads + performance ─────────────────────
        try:
            ad_groups = await self.ads_client.get_ad_groups(campaign_id)
            ad_performance = await self.ads_client.get_ad_performance("LAST_30_DAYS")
            keyword_data = await self.ads_client.get_keyword_performance("LAST_30_DAYS")
        except Exception as e:
            logger.error("Failed to fetch ad data", error=str(e))
            return {"error": f"Could not fetch ad data: {str(e)[:100]}"}

        # Group performance by ad group
        perf_by_ag = {}
        for ad in ad_performance:
            ag_id = ad.get("ad_group_id", "")
            perf_by_ag.setdefault(ag_id, []).append(ad)

        kw_by_ag = {}
        for kw in keyword_data:
            ag_id = kw.get("ad_group_id", "")
            kw_by_ag.setdefault(ag_id, []).append(kw)

        # ── Generate variations per ad group ────────────────────
        results = []
        for ag in ad_groups:
            ag_id = ag.get("ad_group_id", "")
            ag_name = ag.get("name", "Unknown")

            ag_perf = perf_by_ag.get(ag_id, [])
            ag_keywords = kw_by_ag.get(ag_id, [])

            # Fetch actual ads for this ad group
            try:
                ads = await self.ads_client.get_ads(ag_id)
            except Exception:
                ads = []

            # Analyze current performance
            performance = self._analyze_performance(ag_perf)
            winning = self._identify_winners(ag_perf)

            # Call Claude to generate variations
            variations = await self._generate_with_claude(
                ag_name=ag_name,
                current_ads=ads,
                performance=performance,
                winning_elements=winning,
                keywords=ag_keywords,
            )

            if variations:
                results.append({
                    "ad_group_id": ag_id,
                    "ad_group_name": ag_name,
                    "current_performance": performance,
                    "winning_elements": winning,
                    **variations,
                })

        summary = (
            f"Generated variations for {len(results)} ad groups. "
            f"Total: {sum(len(r.get('new_headlines', [])) for r in results)} new headlines, "
            f"{len(results) * 3} angle variants."
        )

        output = {
            "campaign_id": campaign_id,
            "ad_groups": results,
            "summary": summary,
        }

        # ── Log execution ──
        try:
            log = PipelineExecutionLog(
                id=str(uuid.uuid4()),
                tenant_id=self.tenant_id,
                campaign_id=campaign_id,
                conversation_id=conversation_id,
                service_type="ab_generator",
                status="completed",
                completed_at=datetime.now(timezone.utc),
                model_used=self.model,
                input_summary={
                    "campaign_id": campaign_id,
                    "ad_groups_processed": len(results),
                },
                output_summary={
                    "ad_groups": len(results),
                    "new_headlines": sum(len(r.get("new_headlines", [])) for r in results),
                    "angles_generated": len(results) * 3,
                },
                output_full=output,
            )
            self.db.add(log)
            await self.db.flush()
        except Exception as e:
            logger.warning("Failed to save A/B generator log", error=str(e))

        return output

    # ── CLAUDE VARIATION GENERATOR ──────────────────────────────

    async def _generate_with_claude(
        self,
        ag_name: str,
        current_ads: List[Dict],
        performance: Dict,
        winning_elements: List[str],
        keywords: List[Dict],
    ) -> Optional[Dict]:
        """Use Claude Opus to generate smart ad variations."""

        # Extract current headlines/descriptions from ads
        current_headlines = []
        current_descriptions = []
        for ad in current_ads:
            for h in ad.get("headlines", []):
                if isinstance(h, str):
                    current_headlines.append(h)
                elif isinstance(h, dict):
                    current_headlines.append(h.get("text", ""))
            for d in ad.get("descriptions", []):
                if isinstance(d, str):
                    current_descriptions.append(d)
                elif isinstance(d, dict):
                    current_descriptions.append(d.get("text", ""))

        # Top keywords by performance
        top_keywords = sorted(
            keywords,
            key=lambda k: k.get("conversions", 0) * 1000 + k.get("clicks", 0),
            reverse=True,
        )[:10]

        system = """You are an elite Google Ads A/B testing copywriter. You analyze what's WORKING
in current ads and generate smart variations to test.

YOUR APPROACH:
1. KEEP what converts — don't reinvent the wheel. If a headline has high CTR, keep it and vary around it.
2. Test ONE variable at a time — each variation should change ONE thing (angle, CTA, proof point).
3. Use these PROVEN angles:
   - URGENCY: "Available Now", "Same-Day", "Don't Wait", time-limited offers
   - PREMIUM: Position as the expert/specialist, emphasize quality over price
   - PRICE ANCHORING: "Starting at $X", "Free Estimate", transparent pricing
   - SOCIAL PROOF: Reviews, ratings, years in business, jobs completed
   - PROBLEM-SOLUTION: Lead with the customer's pain point

CHARACTER LIMITS ARE ABSOLUTE:
- Headlines: 30 characters max
- Descriptions: 90 characters max

Respond with ONLY valid JSON."""

        user_msg = f"""AD GROUP: {ag_name}

CURRENT HEADLINES (keep winners, improve losers):
{json.dumps(current_headlines[:15], indent=2)}

CURRENT DESCRIPTIONS:
{json.dumps(current_descriptions[:4], indent=2)}

PERFORMANCE DATA:
  CTR: {performance.get('avg_ctr', 0):.2%}
  Conversions: {performance.get('total_conversions', 0)}
  CPC: ${performance.get('avg_cpc', 0):.2f}
  Best performing elements: {json.dumps(winning_elements)}

TOP KEYWORDS (what people actually search):
{json.dumps([kw.get('keyword_text', '') for kw in top_keywords], indent=2)}

Generate A/B test variations. Return this JSON:
{{
  "new_headlines": [
    {{"text": "headline (max 30 chars)", "rationale": "why this might beat current", "test_variable": "urgency|premium|price|proof|problem"}},
    ... (5 new headlines)
  ],
  "new_descriptions": [
    {{"text": "description (max 90 chars)", "rationale": "why test this", "test_variable": "..."}},
    ... (3 new descriptions)
  ],
  "angles": [
    {{
      "name": "urgency",
      "headlines": ["H1 (max 30)", "H2 (max 30)"],
      "descriptions": ["D1 (max 90)"],
      "hypothesis": "Why this angle might convert better"
    }},
    {{
      "name": "premium",
      "headlines": ["H1", "H2"],
      "descriptions": ["D1"],
      "hypothesis": "..."
    }},
    {{
      "name": "price",
      "headlines": ["H1", "H2"],
      "descriptions": ["D1"],
      "hypothesis": "..."
    }}
  ],
  "keep_these": ["headline or description that should NOT change — it's working"],
  "kill_these": ["headline or description that should be replaced — poor performer"]
}}"""

        try:
            response = await self.claude.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.7,
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(raw)

            # Safety: truncate any overlong copy
            for h in result.get("new_headlines", []):
                if isinstance(h, dict) and len(h.get("text", "")) > 30:
                    h["text"] = h["text"][:30]
            for d in result.get("new_descriptions", []):
                if isinstance(d, dict) and len(d.get("text", "")) > 90:
                    d["text"] = d["text"][:90]
            for angle in result.get("angles", []):
                angle["headlines"] = [h[:30] for h in angle.get("headlines", [])]
                angle["descriptions"] = [d[:90] for d in angle.get("descriptions", [])]

            return result

        except Exception as e:
            logger.error("Claude A/B generation failed", error=str(e), ad_group=ag_name)
            return None

    # ── PERFORMANCE ANALYSIS ────────────────────────────────────

    def _analyze_performance(self, ad_perf: List[Dict]) -> Dict:
        """Aggregate ad performance stats."""
        if not ad_perf:
            return {
                "avg_ctr": 0, "avg_cpc": 0, "total_conversions": 0,
                "total_clicks": 0, "total_impressions": 0, "total_cost": 0,
            }

        total_clicks = sum(a.get("clicks", 0) for a in ad_perf)
        total_impressions = sum(a.get("impressions", 0) for a in ad_perf)
        total_cost = sum(a.get("cost_micros", 0) for a in ad_perf) / 1_000_000
        total_conv = sum(a.get("conversions", 0) for a in ad_perf)

        return {
            "avg_ctr": total_clicks / total_impressions if total_impressions > 0 else 0,
            "avg_cpc": total_cost / total_clicks if total_clicks > 0 else 0,
            "total_conversions": total_conv,
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "total_cost": round(total_cost, 2),
        }

    def _identify_winners(self, ad_perf: List[Dict]) -> List[str]:
        """Identify best-performing ad elements."""
        winners = []
        if not ad_perf:
            return winners

        # Sort by CTR descending
        sorted_ads = sorted(
            ad_perf,
            key=lambda a: a.get("ctr", 0),
            reverse=True,
        )

        for ad in sorted_ads[:3]:  # Top 3 ads
            headlines = ad.get("headlines", [])
            if isinstance(headlines, list):
                for h in headlines[:3]:
                    text = h if isinstance(h, str) else h.get("text", "")
                    if text and text not in winners:
                        winners.append(text)

        return winners[:5]
