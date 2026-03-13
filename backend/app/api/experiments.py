from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.core.database import get_db
from app.core.deps import require_tenant, require_analyst, CurrentUser
from app.models.experiment import Experiment

router = APIRouter()


class CreateExperimentRequest(BaseModel):
    name: str
    hypothesis: Optional[str] = None
    entity_scope: Dict[str, Any] = {}
    variants: List[Dict[str, Any]] = []
    success_metric: str = "ctr"
    duration_days: int = 14


class PromoteWinnerRequest(BaseModel):
    winning_variant_index: int


@router.get("")
async def list_experiments(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Experiment).where(Experiment.tenant_id == user.tenant_id)
    if status:
        query = query.where(Experiment.status == status)
    query = query.order_by(desc(Experiment.created_at)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    exps = result.scalars().all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "hypothesis": e.hypothesis,
            "status": e.status,
            "success_metric": e.success_metric,
            "variants": e.variants_json,
            "results": e.results_json,
            "start_at": e.start_at.isoformat() if e.start_at else None,
            "end_at": e.end_at.isoformat() if e.end_at else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in exps
    ]


@router.post("")
async def create_experiment(
    req: CreateExperimentRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)

    exp = Experiment(
        tenant_id=user.tenant_id,
        name=req.name,
        hypothesis=req.hypothesis,
        entity_scope_json=req.entity_scope,
        variants_json=req.variants,
        success_metric=req.success_metric,
        start_at=now,
        end_at=now + timedelta(days=req.duration_days),
        status="draft",
    )
    db.add(exp)
    await db.flush()

    return {"id": exp.id, "status": "draft"}


@router.post("/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Experiment).where(
            Experiment.id == experiment_id,
            Experiment.tenant_id == user.tenant_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status != "draft":
        raise HTTPException(status_code=400, detail=f"Experiment is {exp.status}, cannot start")

    exp.status = "running"
    exp.start_at = datetime.now(__import__("datetime").timezone.utc)
    await db.flush()

    from app.jobs.tasks import start_experiment_task
    start_experiment_task.delay(user.tenant_id, experiment_id)

    return {"id": exp.id, "status": "running"}


@router.post("/{experiment_id}/stop")
async def stop_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Experiment).where(
            Experiment.id == experiment_id,
            Experiment.tenant_id == user.tenant_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    exp.status = "completed"
    exp.end_at = datetime.now(__import__("datetime").timezone.utc)
    await db.flush()

    return {"id": exp.id, "status": "completed"}


@router.post("/{experiment_id}/promote")
async def promote_winner(
    experiment_id: str,
    req: PromoteWinnerRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can promote experiment winners")

    result = await db.execute(
        select(Experiment).where(
            Experiment.id == experiment_id,
            Experiment.tenant_id == user.tenant_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    variants = exp.variants_json or []
    if req.winning_variant_index >= len(variants):
        raise HTTPException(status_code=400, detail="Invalid variant index")

    from app.jobs.tasks import promote_experiment_winner_task
    promote_experiment_winner_task.delay(user.tenant_id, experiment_id, req.winning_variant_index)

    return {"status": "promoting", "variant": req.winning_variant_index}


@router.post("/{experiment_id}/collect-results")
async def collect_results(
    experiment_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Experiment).where(
            Experiment.id == experiment_id,
            Experiment.tenant_id == user.tenant_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status != "running":
        raise HTTPException(status_code=400, detail=f"Experiment is {exp.status}, not running")

    from app.jobs.tasks import collect_experiment_results_task
    collect_experiment_results_task.delay(user.tenant_id, experiment_id)

    return {"status": "collecting", "experiment_id": experiment_id}


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Experiment).where(
            Experiment.id == experiment_id,
            Experiment.tenant_id == user.tenant_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return {
        "id": exp.id,
        "name": exp.name,
        "hypothesis": exp.hypothesis,
        "status": exp.status,
        "success_metric": exp.success_metric,
        "entity_scope": exp.entity_scope_json,
        "variants": exp.variants_json,
        "results": exp.results_json,
        "start_at": exp.start_at.isoformat() if exp.start_at else None,
        "end_at": exp.end_at.isoformat() if exp.end_at else None,
    }
