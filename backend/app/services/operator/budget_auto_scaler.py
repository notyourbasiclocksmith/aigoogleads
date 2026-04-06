"""
Budget Auto-Scaler
==================

ROAS-based budget scaling with safety guardrails.

Logic:
- ROAS > 3.0 → increase budget +20% (making money, scale up)
- ROAS 2.0-3.0 → hold steady (profitable but not crushing it)
- ROAS 1.2-2.0 → reduce budget -10% (barely breaking even)
- ROAS < 1.2 → pause or reduce -30% (losing money)

Confidence Requirements (won't act without sufficient data):
- Minimum 20 clicks
- Minimum 2 conversions
- Minimum 7 days of data
- Budget change cap: max 20% per adjustment, max 50% per week

Kill Switch:
- If keyword has >= 50 clicks and 0 conversions → pause keyword
- If campaign CPA > 3x target CPA → reduce to minimum budget
"""

import time
import uuid
import structlog
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.v2.optimization_cycle import OptimizationCycle
from app.models.pipeline_execution_log import PipelineExecutionLog

logger = structlog.get_logger()

# ── CONFIDENCE THRESHOLDS ───────────────────────────────────
MIN_CLICKS = 20
MIN_CONVERSIONS = 2
MIN_DATA_DAYS = 7

# ── ROAS THRESHOLDS ────────────────────────────────────────
ROAS_SCALE_UP = 3.0        # Scale budget up
ROAS_HOLD = 2.0            # Keep budget steady
ROAS_REDUCE = 1.2          # Reduce budget
# Below ROAS_REDUCE = aggressive reduction

# ── BUDGET LIMITS ───────────────────────────────────────────
MAX_SINGLE_INCREASE_PCT = 20     # Max +20% per adjustment
MAX_SINGLE_DECREASE_PCT = 30     # Max -30% per adjustment
MAX_WEEKLY_CHANGE_PCT = 50       # Max total change per week
MIN_DAILY_BUDGET_MICROS = 5_000_000   # $5/day floor

# ── KILL SWITCHES ───────────────────────────────────────────
KEYWORD_KILL_CLICKS = 50         # Pause keyword after 50 clicks, 0 conversions
CPA_EMERGENCY_MULTIPLIER = 3.0  # If CPA > 3x target → emergency reduce


class BudgetAutoScaler:
    """ROAS-based budget scaling with safety guardrails."""

    def __init__(self, db: AsyncSession, tenant_id: str, ads_client: Any):
        self.db = db
        self.tenant_id = tenant_id
        self.ads_client = ads_client

    async def evaluate_and_scale(
        self,
        campaign_id: str,
        target_cpa_micros: int = 0,
        guardrails: Optional[Dict] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a campaign's performance and recommend/execute budget changes.

        Returns:
        {
            "action": "increase" | "hold" | "decrease" | "emergency_reduce" | "insufficient_data",
            "current_budget_micros": N,
            "recommended_budget_micros": N,
            "change_pct": N,
            "roas": X.X,
            "metrics": {...},
            "confidence": "high" | "medium" | "low" | "insufficient",
            "reasoning": "...",
            "keyword_kills": [...],  # Keywords to pause
        }
        """
        guardrails = guardrails or {}
        max_daily = guardrails.get("max_daily_budget", 0) * 1_000_000  # Convert to micros
        max_increase_pct = guardrails.get("max_budget_increase_pct", MAX_SINGLE_INCREASE_PCT)
        min_roas = guardrails.get("min_roas", ROAS_REDUCE)

        # ── Fetch performance data ──────────────────────────────
        try:
            metrics = await self._get_campaign_metrics(campaign_id)
        except Exception as e:
            logger.error("Failed to fetch campaign metrics", error=str(e))
            return {
                "action": "error",
                "reasoning": f"Could not fetch metrics: {str(e)[:100]}",
            }

        # ── Check confidence ────────────────────────────────────
        confidence = self._assess_confidence(metrics)
        if confidence == "insufficient":
            return {
                "action": "insufficient_data",
                "metrics": metrics,
                "confidence": "insufficient",
                "reasoning": (
                    f"Not enough data to make budget decisions. "
                    f"Need {MIN_CLICKS} clicks (have {metrics.get('clicks', 0)}), "
                    f"{MIN_CONVERSIONS} conversions (have {metrics.get('conversions', 0)}), "
                    f"and {MIN_DATA_DAYS} days of data."
                ),
            }

        # ── Calculate ROAS ──────────────────────────────────────
        cost = metrics.get("cost_micros", 0)
        conv_value = metrics.get("conversions_value_micros", 0)
        roas = (conv_value / cost) if cost > 0 else 0
        conversions = metrics.get("conversions", 0)
        cpa = (cost / conversions) if conversions > 0 else 0

        current_budget = metrics.get("budget_micros", 50_000_000)

        # ── Emergency checks ────────────────────────────────────
        # CPA emergency: if CPA > 3x target
        if target_cpa_micros > 0 and cpa > target_cpa_micros * CPA_EMERGENCY_MULTIPLIER:
            new_budget = max(
                int(current_budget * 0.5),  # Cut 50%
                MIN_DAILY_BUDGET_MICROS,
            )
            return {
                "action": "emergency_reduce",
                "current_budget_micros": current_budget,
                "recommended_budget_micros": new_budget,
                "change_pct": round((new_budget - current_budget) / current_budget * 100, 1),
                "roas": round(roas, 2),
                "cpa": round(cpa / 1_000_000, 2),
                "target_cpa": round(target_cpa_micros / 1_000_000, 2),
                "metrics": metrics,
                "confidence": confidence,
                "reasoning": (
                    f"EMERGENCY: CPA ${cpa/1_000_000:.2f} is {cpa/target_cpa_micros:.1f}x "
                    f"the target CPA ${target_cpa_micros/1_000_000:.2f}. "
                    f"Cutting budget 50% to stop bleeding."
                ),
                "keyword_kills": await self._find_kill_keywords(campaign_id),
            }

        # ── ROAS-based scaling ──────────────────────────────────
        if roas >= ROAS_SCALE_UP:
            # Making great money — scale up
            increase_pct = min(max_increase_pct, MAX_SINGLE_INCREASE_PCT)
            new_budget = int(current_budget * (1 + increase_pct / 100))

            # Respect max daily budget guardrail
            if max_daily > 0:
                new_budget = min(new_budget, int(max_daily))

            # Check weekly change cap
            new_budget = await self._apply_weekly_cap(
                campaign_id, current_budget, new_budget
            )

            action = "increase"
            reasoning = (
                f"ROAS {roas:.1f}x (>{ROAS_SCALE_UP}x threshold). "
                f"Campaign is profitable — increasing budget +{increase_pct}% "
                f"from ${current_budget/1_000_000:.0f} to ${new_budget/1_000_000:.0f}/day."
            )

        elif roas >= ROAS_HOLD:
            # Profitable but not crushing it — hold steady
            new_budget = current_budget
            action = "hold"
            reasoning = (
                f"ROAS {roas:.1f}x (between {ROAS_HOLD}x-{ROAS_SCALE_UP}x). "
                f"Campaign is profitable but not at scale threshold. Holding budget steady."
            )

        elif roas >= min_roas:
            # Barely breaking even — reduce cautiously
            decrease_pct = 10
            new_budget = max(
                int(current_budget * (1 - decrease_pct / 100)),
                MIN_DAILY_BUDGET_MICROS,
            )
            action = "decrease"
            reasoning = (
                f"ROAS {roas:.1f}x (between {min_roas}x-{ROAS_HOLD}x). "
                f"Barely profitable — reducing budget {decrease_pct}% "
                f"from ${current_budget/1_000_000:.0f} to ${new_budget/1_000_000:.0f}/day."
            )

        else:
            # Losing money — significant reduction
            decrease_pct = min(MAX_SINGLE_DECREASE_PCT, 30)
            new_budget = max(
                int(current_budget * (1 - decrease_pct / 100)),
                MIN_DAILY_BUDGET_MICROS,
            )
            action = "decrease"
            reasoning = (
                f"ROAS {roas:.1f}x (<{min_roas}x minimum). "
                f"Campaign is losing money — reducing budget {decrease_pct}% "
                f"from ${current_budget/1_000_000:.0f} to ${new_budget/1_000_000:.0f}/day. "
                f"Review keywords and ad copy."
            )

        result = {
            "action": action,
            "current_budget_micros": current_budget,
            "recommended_budget_micros": new_budget,
            "change_pct": round((new_budget - current_budget) / current_budget * 100, 1) if current_budget > 0 else 0,
            "roas": round(roas, 2),
            "cpa": round(cpa / 1_000_000, 2) if conversions > 0 else None,
            "metrics": metrics,
            "confidence": confidence,
            "reasoning": reasoning,
            "keyword_kills": await self._find_kill_keywords(campaign_id),
        }

        # ── Log execution ──
        await self._log_execution(campaign_id, conversation_id, result)

        return result

    async def _log_execution(self, campaign_id: str, conversation_id: Optional[str], result: Dict):
        """Save execution log for analyst review."""
        try:
            log = PipelineExecutionLog(
                id=str(uuid.uuid4()),
                tenant_id=self.tenant_id,
                campaign_id=campaign_id,
                conversation_id=conversation_id,
                service_type="budget_scaler",
                status="completed",
                completed_at=datetime.now(timezone.utc),
                input_summary={
                    "campaign_id": campaign_id,
                    "action": result.get("action"),
                    "roas": result.get("roas"),
                    "confidence": result.get("confidence"),
                },
                output_summary={
                    "action": result.get("action"),
                    "current_budget": result.get("current_budget_micros", 0) / 1_000_000,
                    "recommended_budget": result.get("recommended_budget_micros", 0) / 1_000_000,
                    "change_pct": result.get("change_pct"),
                    "roas": result.get("roas"),
                    "keyword_kills": len(result.get("keyword_kills", [])),
                },
                output_full=result,
            )
            self.db.add(log)
            await self.db.flush()
        except Exception as e:
            logger.warning("Failed to save budget scaler log", error=str(e))

    # ── KEYWORD KILL SWITCH ─────────────────────────────────────

    async def _find_kill_keywords(self, campaign_id: str) -> List[Dict]:
        """Find keywords with high clicks but zero conversions."""
        kills = []
        try:
            keyword_data = await self.ads_client.get_keyword_performance("LAST_30_DAYS")
            for kw in keyword_data:
                if (
                    kw.get("campaign_id") == campaign_id
                    and kw.get("clicks", 0) >= KEYWORD_KILL_CLICKS
                    and kw.get("conversions", 0) == 0
                ):
                    cost_dollars = kw.get("cost_micros", 0) / 1_000_000
                    kills.append({
                        "keyword_id": kw.get("keyword_id"),
                        "keyword_text": kw.get("keyword_text", ""),
                        "clicks": kw.get("clicks", 0),
                        "cost": round(cost_dollars, 2),
                        "reason": f"{kw.get('clicks')} clicks, 0 conversions, ${cost_dollars:.2f} wasted",
                    })
        except Exception as e:
            logger.warning("Could not check keyword kills", error=str(e))

        return kills

    # ── METRICS FETCHING ────────────────────────────────────────

    async def _get_campaign_metrics(self, campaign_id: str) -> Dict[str, Any]:
        """Fetch campaign performance metrics for ROAS calculation."""
        perf = await self.ads_client.get_performance_metrics("LAST_30_DAYS")

        # Find this campaign's metrics
        campaign_metrics = {}
        if isinstance(perf, list):
            campaign_metrics = next(
                (p for p in perf if p.get("campaign_id") == campaign_id), {}
            )
        elif isinstance(perf, dict):
            campaign_metrics = perf

        # Also get current budget
        campaigns = await self.ads_client.get_campaigns()
        campaign = next(
            (c for c in campaigns if c.get("campaign_id") == campaign_id), {}
        )

        return {
            "clicks": campaign_metrics.get("clicks", 0),
            "impressions": campaign_metrics.get("impressions", 0),
            "cost_micros": campaign_metrics.get("cost_micros", 0),
            "conversions": campaign_metrics.get("conversions", 0),
            "conversions_value_micros": campaign_metrics.get("conversions_value", 0) * 1_000_000,
            "ctr": campaign_metrics.get("ctr", 0),
            "avg_cpc": campaign_metrics.get("average_cpc", 0),
            "budget_micros": campaign.get("budget_micros", 50_000_000),
            "days_active": 30,  # Simplified — could calculate from start date
        }

    # ── CONFIDENCE ASSESSMENT ───────────────────────────────────

    def _assess_confidence(self, metrics: Dict) -> str:
        """Assess how confident we can be in budget decisions."""
        clicks = metrics.get("clicks", 0)
        conversions = metrics.get("conversions", 0)

        if clicks < MIN_CLICKS or conversions < MIN_CONVERSIONS:
            return "insufficient"
        elif clicks >= 100 and conversions >= 10:
            return "high"
        elif clicks >= 50 and conversions >= 5:
            return "medium"
        else:
            return "low"

    # ── WEEKLY CAP ──────────────────────────────────────────────

    async def _apply_weekly_cap(
        self, campaign_id: str, current_budget: int, proposed_budget: int
    ) -> int:
        """Ensure we don't exceed weekly change cap."""
        # Check what budget changes were made this week
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        result = await self.db.execute(
            select(OptimizationCycle)
            .where(
                OptimizationCycle.tenant_id == self.tenant_id,
                OptimizationCycle.started_at >= one_week_ago,
                OptimizationCycle.status == "completed",
            )
        )
        recent_cycles = result.scalars().all()

        # Estimate total budget changes this week from cycle data
        total_change_pct = 0
        for cycle in recent_cycles:
            actions = cycle.actions_json or []
            for action in actions:
                if action.get("action_type") in ("INCREASE_BUDGET", "DECREASE_BUDGET"):
                    total_change_pct += abs(action.get("change_pct", 0))

        # If we've already made big changes this week, cap the new one
        remaining_cap = MAX_WEEKLY_CHANGE_PCT - total_change_pct
        if remaining_cap <= 0:
            logger.info("Weekly budget change cap reached", campaign_id=campaign_id)
            return current_budget

        max_allowed_change = int(current_budget * remaining_cap / 100)
        proposed_change = proposed_budget - current_budget

        if abs(proposed_change) > max_allowed_change:
            capped_budget = current_budget + (
                max_allowed_change if proposed_change > 0 else -max_allowed_change
            )
            logger.info(
                "Budget change capped by weekly limit",
                proposed=proposed_budget,
                capped=capped_budget,
            )
            return capped_budget

        return proposed_budget
