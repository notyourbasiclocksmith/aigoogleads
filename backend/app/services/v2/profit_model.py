"""
Module 2 (partial) — Profit Optimization Model
Computes profit-based CPA targets from business profile data.
"""
from typing import Dict, Any, Optional
from decimal import Decimal
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.business_profile import BusinessProfile

logger = structlog.get_logger()


def compute_profit_targets(
    avg_job_value: float,
    gross_margin_pct: float,
    close_rate_estimate: float,
    refund_rate_estimate: float,
    desired_profit_buffer_pct: float,
) -> Dict[str, Any]:
    """
    Compute profit-based optimization targets.

    expected_profit_per_lead = avg_job_value * gross_margin * close_rate * (1 - refund_rate)
    target_cpa_max = expected_profit_per_lead * (1 - desired_profit_buffer)
    """
    if avg_job_value <= 0 or close_rate_estimate <= 0:
        return {
            "expected_profit_per_lead": 0,
            "target_cpa_max": 0,
            "target_roas": 0,
            "error": "avg_job_value and close_rate_estimate must be positive",
        }

    expected_revenue_per_lead = avg_job_value * close_rate_estimate * (1 - refund_rate_estimate)
    expected_profit_per_lead = expected_revenue_per_lead * gross_margin_pct
    target_cpa_max = expected_profit_per_lead * (1 - desired_profit_buffer_pct)
    target_roas = expected_revenue_per_lead / target_cpa_max if target_cpa_max > 0 else 0

    return {
        "avg_job_value": round(avg_job_value, 2),
        "gross_margin_pct": round(gross_margin_pct, 4),
        "close_rate_estimate": round(close_rate_estimate, 4),
        "refund_rate_estimate": round(refund_rate_estimate, 4),
        "desired_profit_buffer_pct": round(desired_profit_buffer_pct, 4),
        "expected_revenue_per_lead": round(expected_revenue_per_lead, 2),
        "expected_profit_per_lead": round(expected_profit_per_lead, 2),
        "target_cpa_max": round(target_cpa_max, 2),
        "target_roas": round(target_roas, 2),
    }


async def get_profit_targets(db: AsyncSession, tenant_id: str) -> Dict[str, Any]:
    """Load business profile and compute profit targets."""
    stmt = select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    result = await db.execute(stmt)
    bp = result.scalars().first()
    if not bp:
        return {"error": "No business profile found"}

    return compute_profit_targets(
        avg_job_value=float(getattr(bp, "avg_job_value", 0) or 0),
        gross_margin_pct=float(getattr(bp, "gross_margin_pct", 0.5) or 0.5),
        close_rate_estimate=float(getattr(bp, "close_rate_estimate", 0.25) or 0.25),
        refund_rate_estimate=float(getattr(bp, "refund_rate_estimate", 0.05) or 0.05),
        desired_profit_buffer_pct=float(getattr(bp, "desired_profit_buffer_pct", 0.20) or 0.20),
    )


async def update_profit_model(
    db: AsyncSession,
    tenant_id: str,
    avg_job_value: Optional[float] = None,
    gross_margin_pct: Optional[float] = None,
    close_rate_estimate: Optional[float] = None,
    refund_rate_estimate: Optional[float] = None,
    desired_profit_buffer_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Update profit model fields on business profile and return new targets."""
    stmt = select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    result = await db.execute(stmt)
    bp = result.scalars().first()
    if not bp:
        return {"error": "No business profile found"}

    if avg_job_value is not None:
        bp.avg_job_value = avg_job_value
    if gross_margin_pct is not None:
        bp.gross_margin_pct = gross_margin_pct
    if close_rate_estimate is not None:
        bp.close_rate_estimate = close_rate_estimate
    if refund_rate_estimate is not None:
        bp.refund_rate_estimate = refund_rate_estimate
    if desired_profit_buffer_pct is not None:
        bp.desired_profit_buffer_pct = desired_profit_buffer_pct

    return compute_profit_targets(
        avg_job_value=float(bp.avg_job_value or 0),
        gross_margin_pct=float(bp.gross_margin_pct or 0.5),
        close_rate_estimate=float(bp.close_rate_estimate or 0.25),
        refund_rate_estimate=float(bp.refund_rate_estimate or 0.05),
        desired_profit_buffer_pct=float(bp.desired_profit_buffer_pct or 0.20),
    )
