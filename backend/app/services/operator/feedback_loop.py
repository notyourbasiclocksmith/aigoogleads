"""
Feedback Loop — evaluates optimization cycle outcomes 24h after execution.

1. Pulls fresh metrics from Google Ads for the same entities that were changed
2. Compares before/after metrics (cost, conversions, CPA, CTR)
3. Classifies result as improved / degraded / neutral
4. Triggers automatic rollback if degradation exceeds threshold
5. Records learning in OptimizationLearning for future confidence scoring
"""
import uuid
import structlog
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.v2.optimization_cycle import OptimizationCycle
from app.models.v2.optimization_learning import OptimizationLearning
from app.models.v2.operator_change_set import OperatorChangeSet
from app.models.v2.operator_mutation import OperatorMutation
from app.models import IntegrationGoogleAds, PerformanceDaily
from app.core.security import decrypt_token
from app.core.config import settings

logger = structlog.get_logger()

# Thresholds for classifying results
DEGRADATION_CPA_INCREASE_PCT = 25   # CPA increased >25% → degraded
DEGRADATION_CONV_DROP_PCT = 30      # Conversions dropped >30% → degraded
IMPROVEMENT_CPA_DECREASE_PCT = 5    # CPA decreased >5% → improved
IMPROVEMENT_CONV_INCREASE_PCT = 5   # Conversions increased >5% → improved
AUTO_ROLLBACK_CPA_INCREASE_PCT = 40 # CPA increased >40% → auto-rollback


async def evaluate_cycle(cycle_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Evaluate the outcome of an optimization cycle by comparing
    before/after account metrics from PerformanceDaily.
    """
    cycle = await db.get(OptimizationCycle, cycle_id)
    if not cycle:
        return {"status": "error", "error": "Cycle not found"}

    if cycle.feedback_status and cycle.feedback_status != "pending_review":
        return {"status": "already_evaluated", "verdict": cycle.feedback_status}

    # ── Gather before metrics (the 7 days before cycle execution) ──────
    cycle_date = cycle.started_at.date() if cycle.started_at else datetime.now(timezone.utc).date()
    before_start = cycle_date - timedelta(days=8)
    before_end = cycle_date - timedelta(days=1)
    after_start = cycle_date
    after_end = cycle_date + timedelta(days=1)  # 24h window

    before_metrics = await _get_period_metrics(
        db, cycle.tenant_id, before_start, before_end
    )
    after_metrics = await _get_period_metrics(
        db, cycle.tenant_id, after_start, after_end
    )

    if not before_metrics or before_metrics.get("days", 0) == 0:
        cycle.feedback_status = "neutral"
        cycle.feedback_json = {"note": "Insufficient baseline data"}
        cycle.feedback_evaluated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "neutral", "reason": "no_baseline"}

    # Normalize to daily averages
    before_daily = _normalize_daily(before_metrics)
    after_daily = _normalize_daily(after_metrics)

    # ── Compare metrics ────────────────────────────────────────────────
    delta = {}
    for key in ["cost", "conversions", "clicks", "impressions"]:
        b = before_daily.get(key, 0)
        a = after_daily.get(key, 0)
        if b > 0:
            delta[f"{key}_pct"] = round(((a - b) / b) * 100, 2)
        else:
            delta[f"{key}_pct"] = 0.0

    before_cpa = before_daily["cost"] / before_daily["conversions"] if before_daily["conversions"] > 0 else 0
    after_cpa = after_daily["cost"] / after_daily["conversions"] if after_daily["conversions"] > 0 else 0

    if before_cpa > 0:
        delta["cpa_pct"] = round(((after_cpa - before_cpa) / before_cpa) * 100, 2)
    else:
        delta["cpa_pct"] = 0.0

    # ── Classify verdict ───────────────────────────────────────────────
    verdict = "neutral"

    if delta["cpa_pct"] > DEGRADATION_CPA_INCREASE_PCT:
        verdict = "degraded"
    elif delta.get("conversions_pct", 0) < -DEGRADATION_CONV_DROP_PCT:
        verdict = "degraded"
    elif delta["cpa_pct"] < -IMPROVEMENT_CPA_DECREASE_PCT:
        verdict = "improved"
    elif delta.get("conversions_pct", 0) > IMPROVEMENT_CONV_INCREASE_PCT:
        verdict = "improved"

    # ── Auto-rollback if severely degraded ─────────────────────────────
    should_rollback = False
    if delta["cpa_pct"] > AUTO_ROLLBACK_CPA_INCREASE_PCT:
        should_rollback = True
        verdict = "rolled_back"
        logger.warning(
            "Auto-rollback triggered: CPA increased too much",
            cycle_id=cycle_id,
            cpa_increase_pct=delta["cpa_pct"],
        )

    # ── Update cycle ───────────────────────────────────────────────────
    cycle.feedback_status = verdict
    cycle.feedback_json = {
        "before_metrics": before_daily,
        "after_metrics": after_daily,
        "delta": delta,
        "before_cpa": round(before_cpa, 2),
        "after_cpa": round(after_cpa, 2),
        "verdict": verdict,
        "auto_rollback": should_rollback,
    }
    cycle.feedback_evaluated_at = datetime.now(timezone.utc)
    await db.commit()

    # ── Record learnings ───────────────────────────────────────────────
    await _record_learnings(db, cycle, verdict, delta)

    # ── Execute rollback if needed ─────────────────────────────────────
    if should_rollback and cycle.change_set_id:
        await rollback_cycle(cycle_id, db)

    logger.info(
        "Cycle feedback evaluated",
        cycle_id=cycle_id,
        verdict=verdict,
        cpa_delta=delta["cpa_pct"],
        conv_delta=delta.get("conversions_pct", 0),
    )

    return {
        "status": "evaluated",
        "verdict": verdict,
        "delta": delta,
        "auto_rollback": should_rollback,
    }


async def rollback_cycle(cycle_id: str, db: AsyncSession) -> Dict[str, Any]:
    """Rollback all mutations from an optimization cycle via ExecutionEngine."""
    cycle = await db.get(OptimizationCycle, cycle_id)
    if not cycle or not cycle.change_set_id:
        return {"status": "error", "error": "No change set to rollback"}

    from app.services.operator.execution_engine import ExecutionEngine
    engine = ExecutionEngine(db)
    result = await engine.rollback_change_set(cycle.change_set_id)

    cycle.feedback_status = "rolled_back"
    await db.commit()

    logger.info("Cycle rolled back", cycle_id=cycle_id, result=result)
    return result


async def _get_period_metrics(
    db: AsyncSession, tenant_id: str, start_date, end_date
) -> Dict[str, Any]:
    """Get aggregated metrics from PerformanceDaily for a date range."""
    result = await db.execute(
        select(
            func.count(func.distinct(PerformanceDaily.date)).label("days"),
            func.sum(PerformanceDaily.impressions).label("impressions"),
            func.sum(PerformanceDaily.clicks).label("clicks"),
            func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
            func.sum(PerformanceDaily.conversions).label("conversions"),
            func.sum(PerformanceDaily.conv_value).label("conv_value"),
        ).where(
            and_(
                PerformanceDaily.tenant_id == tenant_id,
                PerformanceDaily.entity_type == "campaign",
                PerformanceDaily.date >= start_date,
                PerformanceDaily.date <= end_date,
            )
        )
    )
    row = result.one_or_none()
    if not row:
        return {}

    return {
        "days": row.days or 0,
        "impressions": row.impressions or 0,
        "clicks": row.clicks or 0,
        "cost_micros": row.cost_micros or 0,
        "conversions": float(row.conversions or 0),
        "conv_value": float(row.conv_value or 0),
    }


def _normalize_daily(metrics: Dict[str, Any]) -> Dict[str, float]:
    """Normalize period totals to daily averages."""
    days = max(metrics.get("days", 1), 1)
    return {
        "cost": (metrics.get("cost_micros", 0) / 1_000_000) / days,
        "conversions": metrics.get("conversions", 0) / days,
        "clicks": metrics.get("clicks", 0) / days,
        "impressions": metrics.get("impressions", 0) / days,
    }


async def _record_learnings(
    db: AsyncSession,
    cycle: OptimizationCycle,
    verdict: str,
    delta: Dict[str, float],
) -> None:
    """
    Record one OptimizationLearning per action in the cycle.
    Updates confidence scores using exponential moving average.
    """
    actions = cycle.actions_json or []

    for action in actions:
        action_type = action.get("action_type", "")
        entity_type = action.get("entity_type", "")
        pattern = f"{action_type}_{entity_type}" if entity_type else action_type

        # Check for existing learning with same pattern + action
        result = await db.execute(
            select(OptimizationLearning).where(
                and_(
                    OptimizationLearning.tenant_id == cycle.tenant_id,
                    OptimizationLearning.pattern == pattern,
                    OptimizationLearning.action_type == action_type,
                )
            ).limit(1)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update confidence using exponential moving average
            # New confidence = old * 0.7 + outcome_score * 0.3
            outcome_score = _verdict_to_score(verdict)
            existing.confidence_score = round(
                existing.confidence_score * 0.7 + outcome_score * 0.3, 3
            )
            existing.observation_count += 1
            existing.result = verdict
            existing.result_detail_json = {
                "delta": delta,
                "evaluation_window_days": 1,
            }
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Create new learning
            learning = OptimizationLearning(
                id=str(uuid.uuid4()),
                tenant_id=cycle.tenant_id,
                pattern=pattern,
                pattern_detail_json={
                    "entity_type": entity_type,
                    "action_type": action_type,
                },
                action_type=action_type,
                action_detail_json=action,
                result=verdict,
                result_detail_json={
                    "delta": delta,
                    "evaluation_window_days": 1,
                },
                confidence_score=_verdict_to_score(verdict),
                observation_count=1,
                cycle_id=cycle.id,
            )
            db.add(learning)

    await db.flush()


def _verdict_to_score(verdict: str) -> float:
    """Convert a verdict string to a confidence score."""
    return {
        "improved": 0.8,
        "neutral": 0.5,
        "degraded": 0.2,
        "rolled_back": 0.1,
        "unknown": 0.5,
    }.get(verdict, 0.5)
