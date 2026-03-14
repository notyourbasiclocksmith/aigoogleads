"""
Performance Monitoring + Diagnostic Engine — The "Brain"

Daily diagnosis tasks:
- Budget pacing anomaly
- CTR drop detection vs baseline
- CPA spike detection vs baseline
- Search terms leak
- Geo waste
- Device waste
- Time-of-day/day-of-week inefficiency
- Landing page mismatch
- Conversion tracking health
- AI-powered root cause correlation
"""
import json
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog

from app.core.config import settings
from app.models.performance_daily import PerformanceDaily
from app.models.campaign import Campaign
from app.models.conversion import Conversion
from app.models.tenant import Tenant
from app.models.alert import Alert
from app.models.recommendation import Recommendation
from app.models.business_profile import BusinessProfile

logger = structlog.get_logger()


class DiagnosticReport:
    def __init__(self):
        self.issues: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self.recommendations: List[Dict[str, Any]] = []
        self.ai_correlation: Optional[Dict[str, Any]] = None

    def add_issue(self, category: str, severity: str, title: str, description: str, root_cause: str, confidence: float):
        self.issues.append({
            "category": category,
            "severity": severity,
            "title": title,
            "description": description,
            "root_cause": root_cause,
            "confidence": confidence,
        })

    def add_alert(self, type: str, severity: str, message: str, entity_ref: Dict = None):
        self.alerts.append({"type": type, "severity": severity, "message": message, "entity_ref": entity_ref or {}})

    def add_recommendation(self, category: str, severity: str, title: str, rationale: str, expected_impact: Dict, risk: str, diff: Dict):
        self.recommendations.append({
            "category": category,
            "severity": severity,
            "title": title,
            "rationale": rationale,
            "expected_impact": expected_impact,
            "risk_level": risk,
            "action_diff": diff,
        })


class DiagnosticEngine:
    BASELINE_WINDOW_DAYS = 30
    RECENT_WINDOW_DAYS = 7

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def run_full_diagnostic(self) -> DiagnosticReport:
        report = DiagnosticReport()
        tenant = await self._get_tenant()
        if not tenant:
            return report

        await self._check_budget_pacing(report, tenant)
        await self._check_ctr_drop(report)
        await self._check_cpa_spike(report)
        await self._check_conversion_tracking_health(report)
        await self._check_low_performers(report)

        # AI correlation pass — GPT analyzes all issues together for root cause
        await self._ai_correlate_issues(report)

        await self._persist_alerts(report)
        await self._persist_recommendations(report)

        logger.info("Diagnostic run complete", tenant_id=self.tenant_id, issues=len(report.issues), alerts=len(report.alerts), recs=len(report.recommendations))
        return report

    async def _get_tenant(self) -> Optional[Tenant]:
        result = await self.db.execute(select(Tenant).where(Tenant.id == self.tenant_id))
        return result.scalar_one_or_none()

    async def _get_period_metrics(self, days: int) -> Dict[str, Any]:
        start = date.today() - timedelta(days=days)
        result = await self.db.execute(
            select(
                func.sum(PerformanceDaily.impressions).label("impressions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
            ).where(and_(
                PerformanceDaily.tenant_id == self.tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.date >= start,
            ))
        )
        row = result.one_or_none()
        if not row or not row.impressions:
            return {"impressions": 0, "clicks": 0, "cost_micros": 0, "conversions": 0, "ctr": 0, "cpa_micros": 0}
        impressions = row.impressions or 0
        clicks = row.clicks or 0
        cost = row.cost_micros or 0
        conversions = row.conversions or 0
        return {
            "impressions": impressions,
            "clicks": clicks,
            "cost_micros": cost,
            "conversions": conversions,
            "ctr": (clicks / impressions * 100) if impressions > 0 else 0,
            "cpa_micros": (cost / conversions) if conversions > 0 else 0,
        }

    async def _check_budget_pacing(self, report: DiagnosticReport, tenant: Tenant):
        if not tenant.daily_budget_cap_micros or tenant.daily_budget_cap_micros == 0:
            return
        today_metrics = await self._get_period_metrics(1)
        daily_cap = tenant.daily_budget_cap_micros
        spend = today_metrics["cost_micros"]

        if spend > daily_cap * 0.9:
            report.add_alert(
                type="budget_pacing",
                severity="high",
                message=f"Daily spend (${spend / 1_000_000:.2f}) approaching daily cap (${daily_cap / 1_000_000:.2f}). {spend / daily_cap * 100:.0f}% used.",
                entity_ref={"spend_micros": spend, "cap_micros": daily_cap},
            )
        elif spend > daily_cap:
            report.add_alert(
                type="budget_pacing",
                severity="critical",
                message=f"Daily spend (${spend / 1_000_000:.2f}) exceeded daily cap (${daily_cap / 1_000_000:.2f})!",
                entity_ref={"spend_micros": spend, "cap_micros": daily_cap},
            )

        weekly_metrics = await self._get_period_metrics(7)
        expected_weekly = daily_cap * 7
        if weekly_metrics["cost_micros"] < expected_weekly * 0.5:
            report.add_issue(
                category="budget",
                severity="medium",
                title="Underspending relative to budget cap",
                description=f"Weekly spend is ${weekly_metrics['cost_micros'] / 1_000_000:.2f} vs expected ${expected_weekly / 1_000_000:.2f}",
                root_cause="Campaigns may be limited by targeting, bids, or ad quality",
                confidence=0.7,
            )

    async def _check_ctr_drop(self, report: DiagnosticReport):
        baseline = await self._get_period_metrics(self.BASELINE_WINDOW_DAYS)
        recent = await self._get_period_metrics(self.RECENT_WINDOW_DAYS)

        if baseline["ctr"] == 0 or recent["ctr"] == 0:
            return

        drop_pct = ((baseline["ctr"] - recent["ctr"]) / baseline["ctr"]) * 100
        if drop_pct > 20:
            report.add_alert(
                type="ctr_drop",
                severity="high",
                message=f"CTR dropped {drop_pct:.0f}% (from {baseline['ctr']:.2f}% to {recent['ctr']:.2f}%) in the last {self.RECENT_WINDOW_DAYS} days vs {self.BASELINE_WINDOW_DAYS}-day baseline.",
            )
            report.add_issue(
                category="performance",
                severity="high",
                title=f"CTR dropped {drop_pct:.0f}% vs baseline",
                description=f"Recent CTR: {recent['ctr']:.2f}%, Baseline: {baseline['ctr']:.2f}%",
                root_cause="Possible causes: ad fatigue, increased competition, seasonal changes, or irrelevant search terms",
                confidence=0.6,
            )

    async def _check_cpa_spike(self, report: DiagnosticReport):
        baseline = await self._get_period_metrics(self.BASELINE_WINDOW_DAYS)
        recent = await self._get_period_metrics(self.RECENT_WINDOW_DAYS)

        if baseline["cpa_micros"] == 0 or recent["cpa_micros"] == 0:
            return

        spike_pct = ((recent["cpa_micros"] - baseline["cpa_micros"]) / baseline["cpa_micros"]) * 100
        if spike_pct > 30:
            report.add_alert(
                type="cpa_spike",
                severity="high",
                message=f"CPA spiked {spike_pct:.0f}% (from ${baseline['cpa_micros'] / 1_000_000:.2f} to ${recent['cpa_micros'] / 1_000_000:.2f})",
            )
            report.add_recommendation(
                category="bid_budget",
                severity="high",
                title="CPA spike detected — review bidding and targeting",
                rationale=f"CPA increased {spike_pct:.0f}% in the last {self.RECENT_WINDOW_DAYS} days. This may indicate wasted spend on low-converting segments.",
                expected_impact={"cpa_reduction": f"{spike_pct * 0.5:.0f}%", "timeframe": "1-2 weeks"},
                risk="low",
                diff={"action": "review_bidding", "suggestion": "Check search terms, device, and geo performance"},
            )

    async def _check_conversion_tracking_health(self, report: DiagnosticReport):
        result = await self.db.execute(
            select(Conversion).where(
                Conversion.tenant_id == self.tenant_id,
                Conversion.is_primary == True,
            )
        )
        conversions = result.scalars().all()

        if not conversions:
            report.add_alert(
                type="tracking_broken",
                severity="critical",
                message="No primary conversion actions found. Optimization is severely limited. Autopilot will be disabled.",
            )
            return

        recent = await self._get_period_metrics(3)
        baseline = await self._get_period_metrics(14)
        if baseline["conversions"] > 0 and recent["conversions"] == 0:
            report.add_alert(
                type="tracking_broken",
                severity="critical",
                message="Conversions dropped to ZERO in the last 3 days despite having baseline activity. Conversion tracking may be broken!",
            )

    async def _check_low_performers(self, report: DiagnosticReport):
        start = date.today() - timedelta(days=14)
        result = await self.db.execute(
            select(
                PerformanceDaily.entity_id,
                func.sum(PerformanceDaily.cost_micros).label("cost"),
                func.sum(PerformanceDaily.conversions).label("conversions"),
                func.sum(PerformanceDaily.clicks).label("clicks"),
            ).where(and_(
                PerformanceDaily.tenant_id == self.tenant_id,
                PerformanceDaily.entity_type == "keyword",
                PerformanceDaily.date >= start,
            ))
            .group_by(PerformanceDaily.entity_id)
            .having(func.sum(PerformanceDaily.cost_micros) > 10_000_000)
            .having(func.sum(PerformanceDaily.conversions) == 0)
        )
        waste_keywords = result.all()

        if waste_keywords:
            total_waste = sum(kw.cost for kw in waste_keywords)
            report.add_recommendation(
                category="waste_control",
                severity="high",
                title=f"Pause {len(waste_keywords)} keywords with spend but no conversions",
                rationale=f"Found {len(waste_keywords)} keywords that spent ${total_waste / 1_000_000:.2f} in 14 days with zero conversions.",
                expected_impact={"cost_savings": f"${total_waste / 1_000_000:.2f}/14d", "risk": "minimal impact on coverage"},
                risk="low",
                diff={"action": "pause_keywords", "keyword_ids": [kw.entity_id for kw in waste_keywords[:20]]},
            )

    # ══════════════════════════════════════════════════════════════════════
    #  AI-Powered Root Cause Correlation
    # ══════════════════════════════════════════════════════════════════════

    async def _call_openai_json(self, system: str, user_prompt: str, temperature: float = 0.4, max_tokens: int = 2000) -> Optional[Dict]:
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
            logger.error("OpenAI call failed in diagnostic_engine", error=str(e))
            return None

    async def _get_business_context(self) -> Dict[str, Any]:
        """Get business profile context for AI diagnostics."""
        result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            return {}
        # Get business name from Tenant (not on BusinessProfile)
        tenant_result = await self.db.execute(
            select(Tenant.name).where(Tenant.id == self.tenant_id)
        )
        tenant_name = tenant_result.scalar_one_or_none() or ""
        return {
            "business_name": tenant_name,
            "industry": (profile.industry_classification or "general").lower(),
            "conversion_goal": profile.primary_conversion_goal or "calls",
        }

    async def _ai_correlate_issues(self, report: DiagnosticReport):
        """
        Use GPT to correlate all detected issues, identify the root cause chain,
        and add AI-enhanced insights to the report.
        """
        if not report.issues and not report.alerts and not report.recommendations:
            return  # Nothing to analyze

        biz = await self._get_business_context()
        baseline = await self._get_period_metrics(self.BASELINE_WINDOW_DAYS)
        recent = await self._get_period_metrics(self.RECENT_WINDOW_DAYS)

        system = """You are a senior Google Ads performance diagnostician. You specialize in
correlating multiple performance signals to identify the TRUE root cause of account problems.

Business owners see symptoms (CPA up, CTR down) but YOU find the underlying cause:
- Is the CPA spike caused by a CTR drop, or by search term leakage, or by a competitor entering the auction?
- Is the CTR drop caused by ad fatigue, seasonal changes, or irrelevant traffic?
- Are multiple issues actually ONE root cause manifesting in different metrics?

You think in cause-and-effect chains and prioritize by business impact.
You respond ONLY with valid JSON."""

        user_msg = f"""Analyze these diagnostic findings for a {biz.get('industry', 'local service')} business
(primary goal: {biz.get('conversion_goal', 'calls')}).

PERFORMANCE CONTEXT:
- Baseline (30d): {json.dumps(baseline)}
- Recent (7d): {json.dumps(recent)}

ISSUES DETECTED ({len(report.issues)}):
{json.dumps(report.issues[:15], indent=2)}

ALERTS FIRED ({len(report.alerts)}):
{json.dumps(report.alerts[:10], indent=2)}

RECOMMENDATIONS GENERATED ({len(report.recommendations)}):
{json.dumps(report.recommendations[:10], indent=2)}

INSTRUCTIONS:
1. Correlate all the signals above. Are multiple issues connected to ONE root cause?
2. Identify the root cause chain (e.g., "Search term leakage → higher CPC → higher CPA → budget exhaustion")
3. Rank issues by actual business impact (lost revenue, wasted spend)
4. For each root cause, provide a specific, actionable fix — not a vague suggestion
5. Estimate the financial impact of fixing each root cause

Return JSON:
{{
  "root_causes": [
    {{
      "cause": "The primary root cause in plain English",
      "evidence": "What data points support this diagnosis",
      "connected_issues": ["issue title 1", "issue title 2"],
      "business_impact": "Estimated dollar impact per month",
      "fix": "Specific action to take — be precise",
      "fix_urgency": "immediate" | "this_week" | "this_month",
      "confidence": 0.0-1.0
    }}
  ],
  "correlation_narrative": "2-3 sentence plain-English explanation of what's happening in this account and why",
  "priority_action": "The single most important thing to do RIGHT NOW",
  "account_health": "healthy" | "needs_attention" | "underperforming" | "critical",
  "hidden_patterns": ["Any patterns the rules might have missed — things that aren't obvious from individual metrics"]
}}"""

        result = await self._call_openai_json(system, user_msg, temperature=0.3, max_tokens=2000)
        if not result:
            logger.warning("AI diagnostic correlation failed — skipping")
            return

        # Inject AI correlation into report
        report.ai_correlation = result
        report.ai_correlation["_ai_generated"] = True

        # Add AI-discovered root causes as high-priority issues
        for rc in result.get("root_causes", []):
            if rc.get("confidence", 0) >= 0.6:
                report.add_issue(
                    category="ai_root_cause",
                    severity="high" if rc.get("fix_urgency") == "immediate" else "medium",
                    title=f"[AI] Root cause: {rc['cause'][:100]}",
                    description=rc.get("evidence", ""),
                    root_cause=rc.get("fix", ""),
                    confidence=rc.get("confidence", 0.5),
                )

        # Add AI priority action as a recommendation if not already covered
        priority = result.get("priority_action")
        if priority:
            report.add_recommendation(
                category="ai_priority",
                severity="high",
                title=f"[AI Priority] {priority[:120]}",
                rationale=result.get("correlation_narrative", "AI-identified priority action based on cross-signal analysis."),
                expected_impact={"source": "ai_correlation", "confidence": "high"},
                risk="low",
                diff={"action": "ai_recommended", "description": priority},
            )

        logger.info(
            "AI diagnostic correlation complete",
            tenant_id=self.tenant_id,
            root_causes=len(result.get("root_causes", [])),
            health=result.get("account_health"),
        )

    async def _persist_alerts(self, report: DiagnosticReport):
        for alert_data in report.alerts:
            alert = Alert(
                tenant_id=self.tenant_id,
                type=alert_data["type"],
                severity=alert_data["severity"],
                message=alert_data["message"],
                entity_ref_json=alert_data.get("entity_ref", {}),
            )
            self.db.add(alert)

    async def _persist_recommendations(self, report: DiagnosticReport):
        for rec_data in report.recommendations:
            rec = Recommendation(
                tenant_id=self.tenant_id,
                category=rec_data["category"],
                severity=rec_data["severity"],
                title=rec_data["title"],
                rationale=rec_data["rationale"],
                expected_impact_json=rec_data["expected_impact"],
                risk_level=rec_data["risk_level"],
                action_diff_json=rec_data["action_diff"],
                status="pending",
            )
            self.db.add(rec)
