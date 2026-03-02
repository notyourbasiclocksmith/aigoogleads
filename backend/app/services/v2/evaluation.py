"""
Module 7 — Evaluation Framework (Quality Gates)
Measure recommendation quality over time, playbook leaderboards, regression alerts.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.v2.recommendation_outcome import RecommendationOutcome
from app.models.v2.playbook_stat import PlaybookStat
from app.models.recommendation import Recommendation

logger = structlog.get_logger()


async def record_outcome(
    db: AsyncSession,
    recommendation_id: str,
    window_days: int,
    actual_metrics: Dict[str, float],
    predicted_metrics: Optional[Dict[str, float]] = None,
) -> RecommendationOutcome:
    """Record the actual outcome of a recommendation after N days."""
    delta = {}
    if predicted_metrics:
        for key in predicted_metrics:
            pred = predicted_metrics.get(key, 0)
            actual = actual_metrics.get(key, 0)
            if pred != 0:
                delta[key] = {
                    "predicted": pred,
                    "actual": actual,
                    "error_pct": round(((actual - pred) / abs(pred)) * 100, 2),
                }

    # Label outcome
    labeled = "neutral"
    if actual_metrics.get("conversions_delta", 0) > 0 or actual_metrics.get("roas_delta", 0) > 0:
        labeled = "win"
    elif actual_metrics.get("conversions_delta", 0) < -5 or actual_metrics.get("cpa_delta", 0) > 10:
        labeled = "loss"

    outcome = RecommendationOutcome(
        id=str(uuid.uuid4()),
        recommendation_id=recommendation_id,
        window_days=window_days,
        actual_metrics_json=actual_metrics,
        delta_json=delta,
        labeled_outcome=labeled,
    )
    db.add(outcome)
    return outcome


async def get_scorecards(
    db: AsyncSession,
    tenant_id: Optional[str] = None,
    window_days: int = 30,
) -> Dict[str, Any]:
    """Get recommendation scorecards — win/loss/neutral rates and accuracy."""
    stmt = select(RecommendationOutcome).where(RecommendationOutcome.window_days == window_days)

    if tenant_id:
        stmt = stmt.join(Recommendation, RecommendationOutcome.recommendation_id == Recommendation.id)
        stmt = stmt.where(Recommendation.tenant_id == tenant_id)

    result = await db.execute(stmt)
    outcomes = list(result.scalars().all())

    total = len(outcomes)
    if total == 0:
        return {"total": 0, "win_rate": 0, "loss_rate": 0, "neutral_rate": 0, "avg_error_pct": 0}

    wins = sum(1 for o in outcomes if o.labeled_outcome == "win")
    losses = sum(1 for o in outcomes if o.labeled_outcome == "loss")
    neutrals = total - wins - losses

    # Average prediction error
    errors = []
    for o in outcomes:
        if o.delta_json:
            for key, val in o.delta_json.items():
                if isinstance(val, dict) and "error_pct" in val:
                    errors.append(abs(val["error_pct"]))

    avg_error = round(sum(errors) / len(errors), 2) if errors else 0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "neutrals": neutrals,
        "win_rate": round(wins / total * 100, 1),
        "loss_rate": round(losses / total * 100, 1),
        "neutral_rate": round(neutrals / total * 100, 1),
        "avg_prediction_error_pct": avg_error,
        "window_days": window_days,
    }


async def update_playbook_stats(db: AsyncSession, industry: str, metric_key: str, new_data: dict):
    """Update playbook statistics for a given industry + metric."""
    stmt = select(PlaybookStat).where(
        and_(PlaybookStat.industry == industry, PlaybookStat.metric_key == metric_key)
    )
    result = await db.execute(stmt)
    stat = result.scalars().first()

    if stat:
        existing = stat.stat_json or {}
        existing.update(new_data)
        stat.stat_json = existing
        stat.updated_at = datetime.now(timezone.utc)
    else:
        stat = PlaybookStat(
            id=str(uuid.uuid4()),
            industry=industry,
            metric_key=metric_key,
            stat_json=new_data,
        )
        db.add(stat)
    return stat


async def get_playbook_leaderboard(db: AsyncSession, industry: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get playbook stats, optionally filtered by industry."""
    stmt = select(PlaybookStat)
    if industry:
        stmt = stmt.where(PlaybookStat.industry == industry)
    stmt = stmt.order_by(PlaybookStat.updated_at.desc())

    result = await db.execute(stmt)
    stats = result.scalars().all()
    return [
        {
            "industry": s.industry,
            "metric_key": s.metric_key,
            "stats": s.stat_json,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in stats
    ]


async def check_regression(
    db: AsyncSession,
    tenant_id: Optional[str] = None,
    threshold_error_pct: float = 30.0,
) -> Dict[str, Any]:
    """Check if prediction accuracy has degraded beyond threshold."""
    scorecards_30 = await get_scorecards(db, tenant_id, window_days=30)
    scorecards_7 = await get_scorecards(db, tenant_id, window_days=7)

    regression_detected = False
    details = []

    if scorecards_7.get("avg_prediction_error_pct", 0) > threshold_error_pct:
        regression_detected = True
        details.append(f"7-day avg prediction error ({scorecards_7['avg_prediction_error_pct']}%) exceeds threshold ({threshold_error_pct}%)")

    if scorecards_7.get("loss_rate", 0) > 40:
        regression_detected = True
        details.append(f"7-day loss rate ({scorecards_7['loss_rate']}%) exceeds 40%")

    return {
        "regression_detected": regression_detected,
        "details": details,
        "scorecards_7d": scorecards_7,
        "scorecards_30d": scorecards_30,
    }
