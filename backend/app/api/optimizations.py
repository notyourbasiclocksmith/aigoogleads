from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, require_owner, CurrentUser
from app.models.recommendation import Recommendation
from app.models.approval import Approval
from app.models.change_log import ChangeLog
from app.models.tenant import Tenant

router = APIRouter()


class ApproveRejectRequest(BaseModel):
    notes: Optional[str] = None


class AutonomySettingsRequest(BaseModel):
    autonomy_mode: str  # suggest, semi_auto, full_auto
    risk_tolerance: str  # low, medium, high
    daily_budget_cap_micros: Optional[int] = None
    weekly_change_cap_pct: Optional[int] = None


@router.get("/recommendations")
async def list_recommendations(
    status: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Recommendation).where(Recommendation.tenant_id == user.tenant_id)
    if status:
        query = query.where(Recommendation.status == status)
    if category:
        query = query.where(Recommendation.category == category)
    if severity:
        query = query.where(Recommendation.severity == severity)
    query = query.order_by(desc(Recommendation.created_at)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    recs = result.scalars().all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "severity": r.severity,
            "title": r.title,
            "rationale": r.rationale,
            "expected_impact": r.expected_impact_json,
            "risk_level": r.risk_level,
            "action_diff": r.action_diff_json,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in recs
    ]


@router.post("/recommendations/{rec_id}/approve")
async def approve_recommendation(
    rec_id: str,
    req: ApproveRejectRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only owner/admin can approve recommendations")

    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == rec_id,
            Recommendation.tenant_id == user.tenant_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != "pending":
        raise HTTPException(status_code=400, detail=f"Recommendation is already {rec.status}")

    rec.status = "approved"

    approval = Approval(
        tenant_id=user.tenant_id,
        recommendation_id=rec_id,
        approved_by=user.user_id,
        status="approved",
        notes=req.notes,
    )
    db.add(approval)
    await db.flush()

    from app.jobs.tasks import apply_recommendation_task
    apply_recommendation_task.delay(user.tenant_id, rec_id, user.user_id)

    return {"status": "approved", "recommendation_id": rec_id}


@router.post("/recommendations/{rec_id}/reject")
async def reject_recommendation(
    rec_id: str,
    req: ApproveRejectRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Recommendation).where(
            Recommendation.id == rec_id,
            Recommendation.tenant_id == user.tenant_id,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec.status = "rejected"

    approval = Approval(
        tenant_id=user.tenant_id,
        recommendation_id=rec_id,
        approved_by=user.user_id,
        status="rejected",
        notes=req.notes,
    )
    db.add(approval)
    await db.flush()

    return {"status": "rejected", "recommendation_id": rec_id}


@router.get("/change-log")
async def get_change_log(
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ChangeLog)
        .where(ChangeLog.tenant_id == user.tenant_id)
        .order_by(desc(ChangeLog.applied_at))
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "actor_type": l.actor_type,
            "actor_id": l.actor_id,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "before": l.before_json,
            "after": l.after_json,
            "reason": l.reason,
            "applied_at": l.applied_at.isoformat() if l.applied_at else None,
            "rollback_token": l.rollback_token,
            "is_rolled_back": l.is_rolled_back,
        }
        for l in logs
    ]


@router.post("/rollback/{change_log_id}")
async def rollback_change(
    change_log_id: str,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChangeLog).where(
            ChangeLog.id == change_log_id,
            ChangeLog.tenant_id == user.tenant_id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Change log not found")
    if log.is_rolled_back:
        raise HTTPException(status_code=400, detail="Change already rolled back")

    from app.jobs.tasks import rollback_change_task
    rollback_change_task.delay(user.tenant_id, change_log_id, user.user_id)

    return {"status": "rollback_initiated", "change_log_id": change_log_id}


@router.get("/autonomy")
async def get_autonomy_settings(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    return {
        "autonomy_mode": tenant.autonomy_mode,
        "risk_tolerance": tenant.risk_tolerance,
        "daily_budget_cap_micros": tenant.daily_budget_cap_micros,
        "weekly_change_cap_pct": tenant.weekly_change_cap_pct,
    }


@router.put("/autonomy")
async def update_autonomy_settings(
    req: AutonomySettingsRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.autonomy_mode = req.autonomy_mode
    tenant.risk_tolerance = req.risk_tolerance
    if req.daily_budget_cap_micros is not None:
        tenant.daily_budget_cap_micros = req.daily_budget_cap_micros
    if req.weekly_change_cap_pct is not None:
        tenant.weekly_change_cap_pct = req.weekly_change_cap_pct

    await db.flush()
    return {"status": "updated"}
