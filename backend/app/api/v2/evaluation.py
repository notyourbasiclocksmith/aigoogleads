"""Module 7 — Evaluation Framework API Routes"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.services.v2.evaluation import (
    get_scorecards, get_playbook_leaderboard, check_regression, record_outcome,
)

router = APIRouter()


class RecordOutcomeRequest(BaseModel):
    recommendation_id: str
    window_days: int = 30
    actual_metrics: dict
    predicted_metrics: Optional[dict] = None


@router.get("/scorecards")
async def scorecards(
    tenant_id: Optional[str] = None,
    window_days: int = 30,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    effective_tenant = tenant_id or user.tenant_id
    return await get_scorecards(db, effective_tenant, window_days)


@router.get("/leaderboard")
async def leaderboard(
    industry: Optional[str] = None,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await get_playbook_leaderboard(db, industry)


@router.get("/regression-check")
async def regression_check(
    tenant_id: Optional[str] = None,
    threshold: float = 30.0,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    effective_tenant = tenant_id or user.tenant_id
    return await check_regression(db, effective_tenant, threshold)


@router.post("/record-outcome")
async def record_outcome_endpoint(
    req: RecordOutcomeRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    outcome = await record_outcome(db, req.recommendation_id, req.window_days, req.actual_metrics, req.predicted_metrics)
    return {
        "id": outcome.id,
        "recommendation_id": outcome.recommendation_id,
        "window_days": outcome.window_days,
        "labeled_outcome": outcome.labeled_outcome,
        "delta": outcome.delta_json,
    }
