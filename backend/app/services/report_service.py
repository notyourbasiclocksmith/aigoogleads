"""
Report Service — Weekly AI CMO reports, monthly growth reviews, CSV exports.
"""
import csv
import io
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from app.models.performance_daily import PerformanceDaily
from app.models.campaign import Campaign
from app.models.recommendation import Recommendation
from app.models.change_log import ChangeLog
from app.models.alert import Alert


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

        return {
            "report_type": "weekly",
            "period": {"start": str(start), "end": str(date.today()), "days": period_days},
            "kpis": {
                "current": current,
                "previous": previous,
                "changes": self._compute_deltas(current, previous),
            },
            "wins": self._identify_wins(current, previous),
            "losses": self._identify_losses(current, previous),
            "changes_applied": changes,
            "pending_recommendations": recs,
            "alerts": alerts,
            "next_week_focus": self._suggest_focus(current, previous, recs),
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

    async def export_csv(self, entity_type: str, days: int) -> str:
        start = date.today() - timedelta(days=days)
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
            writer.writerow([
                str(r.date), r.entity_id, r.impressions, r.clicks,
                round(r.cost_micros / 1_000_000, 2), round(r.conversions, 1),
                round(r.ctr, 2), round(r.cpc_micros / 1_000_000, 2), round(r.cpa_micros / 1_000_000, 2),
            ])
        return output.getvalue()
