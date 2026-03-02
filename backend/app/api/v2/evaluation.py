"""Module 7 — Evaluation Framework API Routes"""
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
async def scorecards(tenant_id: Optional[str] = None, window_days: int = 30, db: AsyncSession = Depends(get_db)):
    return await get_scorecards(db, tenant_id, window_days)


@router.get("/leaderboard")
async def leaderboard(industry: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await get_playbook_leaderboard(db, industry)


@router.get("/regression-check")
async def regression_check(tenant_id: Optional[str] = None, threshold: float = 30.0, db: AsyncSession = Depends(get_db)):
    return await check_regression(db, tenant_id, threshold)


@router.post("/record-outcome")
async def record_outcome_endpoint(req: RecordOutcomeRequest, db: AsyncSession = Depends(get_db)):
    outcome = await record_outcome(db, req.recommendation_id, req.window_days, req.actual_metrics, req.predicted_metrics)
    return {
        "id": outcome.id,
        "recommendation_id": outcome.recommendation_id,
        "window_days": outcome.window_days,
        "labeled_outcome": outcome.labeled_outcome,
        "delta": outcome.delta_json,
    }
