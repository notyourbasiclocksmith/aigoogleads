"""
Report Service — Weekly AI CMO reports, monthly growth reviews, CSV exports.
"""
import csv
import io
import json
from datetime import date, timedelta
from typing import Optional, Dict, Any
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
import structlog

from app.core.config import settings
from app.models.performance_daily import PerformanceDaily
from app.models.campaign import Campaign
from app.models.recommendation import Recommendation
from app.models.change_log import ChangeLog
from app.models.alert import Alert
from app.models.business_profile import BusinessProfile

logger = structlog.get_logger()


class ReportService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def generate_weekly_report(self, period_days: int = 7) -> dict:
        start = date.today() - timedelta(days=period_days)
        prev_start = start - timedelta(days=period_days)

        current = await self._get_period_summary(start, date.today())
        previous = await self._get_period_summary(prev_start, start)
        changes = await self._get_recent_changes(period_days)
        recs = await self._get_pending_recommendations()
        alerts = await self._get_recent_alerts(period_days)

        deltas = self._compute_deltas(current, previous)
        wins = self._identify_wins(current, previous)
        losses = self._identify_losses(current, previous)
        focus = self._suggest_focus(current, previous, recs)

        # Generate AI narrative
        ai_narrative = await self._generate_ai_narrative(
            current=current, previous=previous, deltas=deltas,
            wins=wins, losses=losses, changes=changes,
            recs=recs, alerts=alerts, focus=focus,
            period_days=period_days,
        )

        return {
            "report_type": "weekly",
            "period": {"start": str(start), "end": str(date.today()), "days": period_days},
            "kpis": {
                "current": current,
                "previous": previous,
                "changes": deltas,
            },
            "wins": wins,
            "losses": losses,
            "changes_applied": changes,
            "pending_recommendations": recs,
            "alerts": alerts,
            "next_week_focus": focus,
            "ai_narrative": ai_narrative,
        }

    async def _get_period_summary(self, start: date, end: date) -> dict:
        result = await self.db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
                func.sum(PerformanceDaily.conv_value).label("conv_value"),
            ).where(and_(
                PerformanceDaily.tenant_id == self.tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.date >= start,
                PerformanceDaily.date < end,
            ))
        )
        row = result.one_or_none()
        imp = row.impressions or 0 if row else 0
        clicks = row.clicks or 0 if row else 0
        cost = row.cost_micros or 0 if row else 0
        conv = row.conversions or 0 if row else 0
        val = row.conv_value or 0 if row else 0
        return {
            "impressions": imp,
            "clicks": clicks,
            "cost": round(cost / 1_000_000, 2),
            "conversions": round(conv, 1),
            "conv_value": round(val, 2),
            "ctr": round((clicks / imp * 100) if imp > 0 else 0, 2),
            "cpc": round((cost / clicks / 1_000_000) if clicks > 0 else 0, 2),
            "cpa": round((cost / conv / 1_000_000) if conv > 0 else 0, 2),
        }

    def _compute_deltas(self, current: dict, previous: dict) -> dict:
        deltas = {}
        for key in ["impressions", "clicks", "cost", "conversions", "ctr", "cpc", "cpa"]:
            c = current.get(key, 0)
            p = previous.get(key, 0)
            if p > 0:
                deltas[key] = round(((c - p) / p) * 100, 1)
            else:
                deltas[key] = 0
        return deltas

    def _identify_wins(self, current: dict, previous: dict) -> list:
        wins = []
        if current["conversions"] > previous["conversions"]:
            wins.append(f"Conversions up {current['conversions'] - previous['conversions']:.0f}")
        if current["cpa"] < previous["cpa"] and current["cpa"] > 0:
            wins.append(f"CPA improved from ${previous['cpa']:.2f} to ${current['cpa']:.2f}")
        if current["ctr"] > previous["ctr"]:
            wins.append(f"CTR improved from {previous['ctr']:.2f}% to {current['ctr']:.2f}%")
        return wins

    def _identify_losses(self, current: dict, previous: dict) -> list:
        losses = []
        if current["conversions"] < previous["conversions"] and previous["conversions"] > 0:
            losses.append(f"Conversions down {previous['conversions'] - current['conversions']:.0f}")
        if current["cpa"] > previous["cpa"] * 1.2 and current["cpa"] > 0:
            losses.append(f"CPA increased from ${previous['cpa']:.2f} to ${current['cpa']:.2f}")
        if current["ctr"] < previous["ctr"] * 0.8 and previous["ctr"] > 0:
            losses.append(f"CTR dropped from {previous['ctr']:.2f}% to {current['ctr']:.2f}%")
        return losses

    async def _get_recent_changes(self, days: int) -> list:
        start = date.today() - timedelta(days=days)
        result = await self.db.execute(
            select(ChangeLog)
            .where(and_(ChangeLog.tenant_id == self.tenant_id, ChangeLog.applied_at >= start.isoformat()))
            .order_by(desc(ChangeLog.applied_at))
            .limit(20)
        )
        logs = result.scalars().all()
        return [{"entity_type": l.entity_type, "reason": l.reason, "actor_type": l.actor_type} for l in logs]

    async def _get_pending_recommendations(self) -> list:
        result = await self.db.execute(
            select(Recommendation)
            .where(and_(Recommendation.tenant_id == self.tenant_id, Recommendation.status == "pending"))
            .limit(10)
        )
        recs = result.scalars().all()
        return [{"title": r.title, "category": r.category, "severity": r.severity} for r in recs]

    async def _get_recent_alerts(self, days: int) -> list:
        start = date.today() - timedelta(days=days)
        result = await self.db.execute(
            select(Alert)
            .where(and_(Alert.tenant_id == self.tenant_id, Alert.created_at >= start.isoformat()))
            .order_by(desc(Alert.created_at))
            .limit(10)
        )
        alerts = result.scalars().all()
        return [{"type": a.type, "severity": a.severity, "message": a.message} for a in alerts]

    def _suggest_focus(self, current: dict, previous: dict, recs: list) -> list:
        focus = []
        high_recs = [r for r in recs if r["severity"] == "high"]
        if high_recs:
            focus.append(f"Review {len(high_recs)} high-priority recommendations")
        if current["cpa"] > previous["cpa"] * 1.1:
            focus.append("Investigate CPA increase — check search terms and targeting")
        if current["conversions"] == 0:
            focus.append("URGENT: Check conversion tracking — zero conversions detected")
        if not focus:
            focus.append("Continue monitoring performance and reviewing recommendations")
        return focus

    # ══════════════════════════════════════════════════════════════════════
    #  AI-Powered CMO Narrative Report
    # ══════════════════════════════════════════════════════════════════════

    async def _call_openai_json(self, system: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> Optional[Dict[str, Any]]:
        """Call OpenAI and parse JSON response. Returns None on any failure."""
        if not settings.OPENAI_API_KEY:
            return None
        try:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model=getattr(settings, "OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            if not content:
                return None
            return json.loads(content)
        except Exception as e:
            logger.error("OpenAI call failed in report_service", error=str(e))
            return None

    async def _get_business_context(self) -> Dict[str, Any]:
        """Get business profile context for richer AI narratives."""
        result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return {}
        return {
            "business_name": getattr(profile, "business_name", ""),
            "industry": (profile.industry_classification or "general").lower(),
            "conversion_goal": profile.primary_conversion_goal or "calls",
            "website": profile.website_url or "",
        }

    async def _get_campaign_breakdown(self, period_days: int) -> list:
        """Get per-campaign performance for the period."""
        start = date.today() - timedelta(days=period_days)
        result = await self.db.execute(
            select(
                Campaign.name,
                Campaign.type,
                Campaign.status,
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
            )
            .join(PerformanceDaily, and_(
                PerformanceDaily.entity_id == Campaign.campaign_id,
                PerformanceDaily.tenant_id == Campaign.tenant_id,
                PerformanceDaily.entity_type == "campaign",
            ))
            .where(Campaign.tenant_id == self.tenant_id, PerformanceDaily.date >= start)
            .group_by(Campaign.name, Campaign.type, Campaign.status)
            .order_by(desc(func.sum(PerformanceDaily.cost_micros)))
            .limit(10)
        )
        rows = result.all()
        breakdown = []
        for r in rows:
            imp = int(r.impressions or 0)
            clicks = int(r.clicks or 0)
            cost = float(r.cost_micros or 0) / 1_000_000
            conv = float(r.conversions or 0)
            breakdown.append({
                "name": r.name, "type": r.type, "status": r.status,
                "impressions": imp, "clicks": clicks,
                "cost": round(cost, 2), "conversions": round(conv, 1),
                "ctr": round((clicks / imp * 100) if imp > 0 else 0, 2),
                "cpc": round((cost / clicks) if clicks > 0 else 0, 2),
                "cpa": round((cost / conv) if conv > 0 else 0, 2),
            })
        return breakdown

    async def _generate_ai_narrative(
        self, current: dict, previous: dict, deltas: dict,
        wins: list, losses: list, changes: list,
        recs: list, alerts: list, focus: list,
        period_days: int,
    ) -> Optional[Dict[str, Any]]:
        """Use GPT to generate a CMO-style narrative performance report."""
        biz = await self._get_business_context()
        campaign_breakdown = await self._get_campaign_breakdown(period_days)

        system = """You are a fractional CMO for a local service business running Google Ads.
You write concise, actionable weekly performance reports for business owners who are NOT
marketing experts. You explain what happened, why it matters, and what to do next.

You are direct, data-driven, and avoid jargon. When something is going well, you celebrate
briefly. When something is wrong, you explain the root cause and give a specific action item.

You respond ONLY with valid JSON."""

        user_msg = f"""Write the weekly Google Ads performance report for this business.

BUSINESS CONTEXT:
- Business: {biz.get('business_name', 'N/A')}
- Industry: {biz.get('industry', 'general')}
- Primary goal: {biz.get('conversion_goal', 'calls')}
- Report period: last {period_days} days

THIS WEEK'S PERFORMANCE:
- Impressions: {current['impressions']:,} ({deltas.get('impressions', 0):+.1f}% vs prior)
- Clicks: {current['clicks']:,} ({deltas.get('clicks', 0):+.1f}%)
- Cost: ${current['cost']:,.2f} ({deltas.get('cost', 0):+.1f}%)
- Conversions: {current['conversions']} ({deltas.get('conversions', 0):+.1f}%)
- CTR: {current['ctr']}% ({deltas.get('ctr', 0):+.1f}%)
- CPC: ${current['cpc']} ({deltas.get('cpc', 0):+.1f}%)
- CPA: ${current['cpa']} ({deltas.get('cpa', 0):+.1f}%)

PRIOR PERIOD PERFORMANCE:
- Impressions: {previous['impressions']:,}
- Clicks: {previous['clicks']:,}
- Cost: ${previous['cost']:,.2f}
- Conversions: {previous['conversions']}
- CTR: {previous['ctr']}%
- CPC: ${previous['cpc']}
- CPA: ${previous['cpa']}

CAMPAIGN BREAKDOWN (top campaigns):
{json.dumps(campaign_breakdown[:8], indent=2)}

WINS IDENTIFIED: {json.dumps(wins)}
LOSSES IDENTIFIED: {json.dumps(losses)}

CHANGES APPLIED THIS PERIOD ({len(changes)} total):
{json.dumps(changes[:10], indent=2)}

ACTIVE ALERTS ({len(alerts)}):
{json.dumps(alerts[:5], indent=2)}

PENDING RECOMMENDATIONS ({len(recs)}):
{json.dumps(recs[:8], indent=2)}

SUGGESTED FOCUS AREAS: {json.dumps(focus)}

Write a comprehensive but concise CMO report. Return JSON:
{{
  "executive_summary": "2-3 sentence TL;DR of the week — what happened and what it means for the business",
  "performance_analysis": "3-5 sentence deep analysis of the numbers — what drove changes and why",
  "campaign_highlights": [
    {{"campaign": "name", "insight": "what happened and why it matters"}}
  ],
  "wins_narrative": "1-2 sentences celebrating what went well (or 'No significant wins this period' if none)",
  "concerns": [
    {{"issue": "what's wrong", "impact": "business impact", "action": "specific next step"}}
  ],
  "recommendations_summary": "2-3 sentences about the most important pending recommendations and why they matter",
  "next_week_plan": [
    "Specific action item 1",
    "Specific action item 2",
    "Specific action item 3"
  ],
  "health_score": 1-10,
  "health_score_reasoning": "Why this score — what's working and what needs attention",
  "trend_direction": "improving" | "stable" | "declining",
  "estimated_monthly_projection": {{
    "conversions": estimated_monthly_conversions,
    "cost": estimated_monthly_cost,
    "cpa": estimated_monthly_cpa
  }}
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.5, max_tokens=2500)
        if result:
            result["_ai_generated"] = True
            logger.info("AI CMO narrative generated", tenant_id=self.tenant_id)
            return result

        # Fallback: simple template narrative
        logger.warning("AI narrative failed — using template fallback")
        return {
            "executive_summary": (
                f"This week: {current['clicks']:,} clicks, {current['conversions']} conversions "
                f"at ${current['cpa']} CPA. "
                + (f"Conversions {'up' if deltas.get('conversions', 0) > 0 else 'down'} "
                   f"{abs(deltas.get('conversions', 0)):.0f}% vs last period."
                   if deltas.get('conversions', 0) != 0 else "Performance flat vs last period.")
            ),
            "performance_analysis": f"Spent ${current['cost']:,.2f} with a {current['ctr']}% CTR.",
            "wins_narrative": "; ".join(wins) if wins else "No significant wins this period.",
            "concerns": [{"issue": l, "impact": "Monitor closely", "action": "Review in detail"} for l in losses],
            "next_week_plan": focus,
            "health_score": 5,
            "health_score_reasoning": "Template-generated — AI unavailable for deeper analysis.",
            "trend_direction": "improving" if deltas.get("conversions", 0) > 0 else ("declining" if deltas.get("conversions", 0) < 0 else "stable"),
            "_ai_generated": False,
        }

    async def export_csv(self, entity_type: str, days: int) -> str:
        start = date.today() - timedelta(days=days)

        if entity_type == "campaigns":
            return await self._export_campaigns(start)
        elif entity_type == "keywords":
            return await self._export_keywords(start)
        elif entity_type == "search_terms":
            return await self._export_search_terms(start)
        elif entity_type == "ads":
            return await self._export_ads(start)
        elif entity_type == "auction_insights":
            return await self._export_auction_insights(start)
        else:
            # Fallback: raw performance_daily
            return await self._export_performance_daily(entity_type, start)

    async def _export_performance_daily(self, entity_type: str, start: date) -> str:
        result = await self.db.execute(
            select(PerformanceDaily)
            .where(and_(
                PerformanceDaily.tenant_id == self.tenant_id,
                PerformanceDaily.entity_type == entity_type,
                PerformanceDaily.date >= start,
            ))
            .order_by(PerformanceDaily.date)
        )
        rows = result.scalars().all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "entity_id", "impressions", "clicks", "cost", "conversions", "ctr", "cpc", "cpa"])
        for r in rows:
            imp = r.impressions or 0
            clicks = r.clicks or 0
            cost = (r.cost_micros or 0) / 1_000_000
            conv = r.conversions or 0
            writer.writerow([
                str(r.date), r.entity_id, imp, clicks,
                round(cost, 2), round(conv, 1),
                round(r.ctr or 0, 2),
                round((r.cpc_micros or 0) / 1_000_000, 2),
                round((r.cpa_micros or 0) / 1_000_000, 2),
            ])
        return output.getvalue()

    async def _export_campaigns(self, start: date) -> str:
        result = await self.db.execute(
            select(
                Campaign.name,
                Campaign.campaign_id,
                Campaign.status,
                Campaign.type,
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
                func.sum(PerformanceDaily.conv_value).label("conv_value"),
            )
            .join(PerformanceDaily, and_(
                PerformanceDaily.entity_id == Campaign.campaign_id,
                PerformanceDaily.tenant_id == Campaign.tenant_id,
                PerformanceDaily.entity_type == "campaign",
            ))
            .where(Campaign.tenant_id == self.tenant_id, PerformanceDaily.date >= start)
            .group_by(Campaign.name, Campaign.campaign_id, Campaign.status, Campaign.type)
            .order_by(desc(func.sum(PerformanceDaily.cost_micros)))
        )
        rows = result.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["campaign_name", "campaign_id", "status", "type", "impressions", "clicks", "cost", "conversions", "revenue", "ctr", "cpc", "cpa", "roas"])
        for r in rows:
            imp = int(r.impressions or 0)
            clicks = int(r.clicks or 0)
            cost = float(r.cost_micros or 0) / 1_000_000
            conv = float(r.conversions or 0)
            val = float(r.conv_value or 0)
            writer.writerow([
                r.name, r.campaign_id, r.status, r.type, imp, clicks,
                round(cost, 2), round(conv, 1), round(val, 2),
                round((clicks / imp * 100) if imp > 0 else 0, 2),
                round((cost / clicks) if clicks > 0 else 0, 2),
                round((cost / conv) if conv > 0 else 0, 2),
                round((val / cost) if cost > 0 else 0, 2),
            ])
        return output.getvalue()

    async def _export_keywords(self, start: date) -> str:
        from app.models.keyword_performance_daily import KeywordPerformanceDaily
        result = await self.db.execute(
            select(
                KeywordPerformanceDaily.keyword_text,
                KeywordPerformanceDaily.keyword_id,
                KeywordPerformanceDaily.match_type,
                KeywordPerformanceDaily.campaign_id,
                func.sum(KeywordPerformanceDaily.impressions).label("impressions"),
                func.sum(KeywordPerformanceDaily.clicks).label("clicks"),
                func.sum(KeywordPerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(KeywordPerformanceDaily.conversions).label("conversions"),
                func.sum(KeywordPerformanceDaily.conversion_value).label("conversion_value"),
                func.max(KeywordPerformanceDaily.quality_score).label("quality_score"),
            )
            .where(KeywordPerformanceDaily.tenant_id == self.tenant_id, KeywordPerformanceDaily.date >= start)
            .group_by(
                KeywordPerformanceDaily.keyword_text, KeywordPerformanceDaily.keyword_id,
                KeywordPerformanceDaily.match_type, KeywordPerformanceDaily.campaign_id,
            )
            .order_by(desc(func.sum(KeywordPerformanceDaily.cost_micros)))
        )
        rows = result.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["keyword", "keyword_id", "match_type", "campaign_id", "impressions", "clicks", "cost", "conversions", "revenue", "ctr", "cpc", "quality_score"])
        for r in rows:
            imp = int(r.impressions or 0)
            clicks = int(r.clicks or 0)
            cost = float(r.cost_micros or 0) / 1_000_000
            writer.writerow([
                r.keyword_text, r.keyword_id, r.match_type, r.campaign_id, imp, clicks,
                round(cost, 2), round(float(r.conversions or 0), 1), round(float(r.conversion_value or 0), 2),
                round((clicks / imp * 100) if imp > 0 else 0, 2),
                round((cost / clicks) if clicks > 0 else 0, 2),
                r.quality_score,
            ])
        return output.getvalue()

    async def _export_search_terms(self, start: date) -> str:
        from app.models.search_term_performance import SearchTermPerformance
        result = await self.db.execute(
            select(
                SearchTermPerformance.search_term,
                SearchTermPerformance.keyword_text,
                SearchTermPerformance.campaign_id,
                func.sum(SearchTermPerformance.impressions).label("impressions"),
                func.sum(SearchTermPerformance.clicks).label("clicks"),
                func.sum(SearchTermPerformance.cost_micros).label("cost_micros"),
                func.sum(SearchTermPerformance.conversions).label("conversions"),
                func.sum(SearchTermPerformance.conversion_value).label("conversion_value"),
            )
            .where(SearchTermPerformance.tenant_id == self.tenant_id, SearchTermPerformance.date >= start)
            .group_by(SearchTermPerformance.search_term, SearchTermPerformance.keyword_text, SearchTermPerformance.campaign_id)
            .order_by(desc(func.sum(SearchTermPerformance.cost_micros)))
        )
        rows = result.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["search_term", "keyword", "campaign_id", "impressions", "clicks", "cost", "conversions", "revenue", "ctr", "cpc"])
        for r in rows:
            imp = int(r.impressions or 0)
            clicks = int(r.clicks or 0)
            cost = float(r.cost_micros or 0) / 1_000_000
            writer.writerow([
                r.search_term, r.keyword_text, r.campaign_id, imp, clicks,
                round(cost, 2), round(float(r.conversions or 0), 1), round(float(r.conversion_value or 0), 2),
                round((clicks / imp * 100) if imp > 0 else 0, 2),
                round((cost / clicks) if clicks > 0 else 0, 2),
            ])
        return output.getvalue()

    async def _export_ads(self, start: date) -> str:
        from app.models.ad_performance_daily import AdPerformanceDaily
        result = await self.db.execute(
            select(
                AdPerformanceDaily.ad_id,
                AdPerformanceDaily.campaign_id,
                AdPerformanceDaily.ad_group_id,
                func.sum(AdPerformanceDaily.impressions).label("impressions"),
                func.sum(AdPerformanceDaily.clicks).label("clicks"),
                func.sum(AdPerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(AdPerformanceDaily.conversions).label("conversions"),
                func.sum(AdPerformanceDaily.conversion_value).label("conversion_value"),
            )
            .where(AdPerformanceDaily.tenant_id == self.tenant_id, AdPerformanceDaily.date >= start)
            .group_by(AdPerformanceDaily.ad_id, AdPerformanceDaily.campaign_id, AdPerformanceDaily.ad_group_id)
            .order_by(desc(func.sum(AdPerformanceDaily.cost_micros)))
        )
        rows = result.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ad_id", "campaign_id", "ad_group_id", "impressions", "clicks", "cost", "conversions", "revenue", "ctr", "cpc"])
        for r in rows:
            imp = int(r.impressions or 0)
            clicks = int(r.clicks or 0)
            cost = float(r.cost_micros or 0) / 1_000_000
            writer.writerow([
                r.ad_id, r.campaign_id, r.ad_group_id, imp, clicks,
                round(cost, 2), round(float(r.conversions or 0), 1), round(float(r.conversion_value or 0), 2),
                round((clicks / imp * 100) if imp > 0 else 0, 2),
                round((cost / clicks) if clicks > 0 else 0, 2),
            ])
        return output.getvalue()

    async def _export_auction_insights(self, start: date) -> str:
        from app.models.auction_insight import AuctionInsight
        result = await self.db.execute(
            select(AuctionInsight)
            .where(AuctionInsight.tenant_id == self.tenant_id, AuctionInsight.date >= start)
            .order_by(desc(AuctionInsight.impression_share))
        )
        rows = result.scalars().all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "campaign_id", "competitor_domain", "impression_share", "overlap_rate", "outranking_share", "top_of_page_rate", "abs_top_rate", "position_above_rate"])
        for r in rows:
            writer.writerow([
                str(r.date), r.campaign_id, r.competitor_domain,
                round(r.impression_share or 0, 4), round(r.overlap_rate or 0, 4),
                round(r.outranking_share or 0, 4), round(r.top_of_page_rate or 0, 4),
                round(r.abs_top_rate or 0, 4), round(r.position_above_rate or 0, 4),
            ])
        return output.getvalue()
