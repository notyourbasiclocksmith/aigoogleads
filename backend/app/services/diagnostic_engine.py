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
"""
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog

from app.models.performance_daily import PerformanceDaily
from app.models.campaign import Campaign
from app.models.conversion import Conversion
from app.models.tenant import Tenant
from app.models.alert import Alert
from app.models.recommendation import Recommendation

logger = structlog.get_logger()


class DiagnosticReport:
    def __init__(self):
        self.issues: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self.recommendations: List[Dict[str, Any]] = []

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
