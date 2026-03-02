"""Module 3 — Advanced Change Management API Routes"""
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.v2.change_management import (
    create_change_set, get_change_sets, apply_change_set, rollback_change_set,
    get_freeze_windows, create_freeze_window, delete_freeze_window,
    get_rollback_policy, save_rollback_policy, is_frozen,
)

router = APIRouter()


class CreateChangeSetRequest(BaseModel):
    tenant_id: str
    name: str
    change_log_ids: List[str]
    scheduled_for: Optional[str] = None
    created_by: Optional[str] = None


class ApplyChangeSetRequest(BaseModel):
    tenant_id: str
    change_set_id: str


class RollbackChangeSetRequest(BaseModel):
    tenant_id: str
    change_set_id: str


class CreateFreezeWindowRequest(BaseModel):
    tenant_id: str
    start_at: str
    end_at: str
    reason: str


class DeleteFreezeWindowRequest(BaseModel):
    tenant_id: str
    window_id: str


class SaveRollbackPolicyRequest(BaseModel):
    tenant_id: str
    rules: list
    enabled: bool = True


# ── Change Sets ──
@router.post("/change-sets/create")
async def create_change_set_endpoint(req: CreateChangeSetRequest, db: AsyncSession = Depends(get_db)):
    scheduled = datetime.fromisoformat(req.scheduled_for) if req.scheduled_for else None
    cs = await create_change_set(db, req.tenant_id, req.name, req.change_log_ids, scheduled, req.created_by)
    return {
        "id": cs.id, "name": cs.name, "status": cs.status,
        "scheduled_for": cs.scheduled_for.isoformat() if cs.scheduled_for else None,
        "items_count": len(cs.items),
    }


@router.get("/change-sets")
async def list_change_sets(tenant_id: str, db: AsyncSession = Depends(get_db)):
    sets = await get_change_sets(db, tenant_id)
    return [
        {
            "id": cs.id, "name": cs.name, "status": cs.status,
            "scheduled_for": cs.scheduled_for.isoformat() if cs.scheduled_for else None,
            "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
            "rolled_back_at": cs.rolled_back_at.isoformat() if cs.rolled_back_at else None,
            "items_count": len(cs.items),
            "created_at": cs.created_at.isoformat(),
        }
        for cs in sets
    ]


@router.post("/change-sets/apply")
async def apply_change_set_endpoint(req: ApplyChangeSetRequest, db: AsyncSession = Depends(get_db)):
    result = await apply_change_set(db, req.tenant_id, req.change_set_id)
    if not result.get("applied"):
        raise HTTPException(400, result.get("error", "Failed to apply change set"))
    return result


@router.post("/change-sets/schedule")
async def schedule_change_set(req: CreateChangeSetRequest, db: AsyncSession = Depends(get_db)):
    if not req.scheduled_for:
        raise HTTPException(400, "scheduled_for is required")
    scheduled = datetime.fromisoformat(req.scheduled_for)
    cs = await create_change_set(db, req.tenant_id, req.name, req.change_log_ids, scheduled, req.created_by)
    return {"id": cs.id, "status": "scheduled", "scheduled_for": cs.scheduled_for.isoformat()}


@router.post("/change-sets/rollback")
async def rollback_change_set_endpoint(req: RollbackChangeSetRequest, db: AsyncSession = Depends(get_db)):
    result = await rollback_change_set(db, req.tenant_id, req.change_set_id)
    if not result.get("rolled_back"):
        raise HTTPException(400, result.get("error", "Failed to rollback"))
    return result


# ── Freeze Windows ──
@router.get("/freeze-windows")
async def list_freeze_windows(tenant_id: str, db: AsyncSession = Depends(get_db)):
    windows = await get_freeze_windows(db, tenant_id)
    return [
        {"id": w.id, "start_at": w.start_at.isoformat(), "end_at": w.end_at.isoformat(), "reason": w.reason}
        for w in windows
    ]


@router.post("/freeze-windows")
async def create_freeze_window_endpoint(req: CreateFreezeWindowRequest, db: AsyncSession = Depends(get_db)):
    start = datetime.fromisoformat(req.start_at)
    end = datetime.fromisoformat(req.end_at)
    if end <= start:
        raise HTTPException(400, "end_at must be after start_at")
    window = await create_freeze_window(db, req.tenant_id, start, end, req.reason)
    return {"id": window.id, "start_at": window.start_at.isoformat(), "end_at": window.end_at.isoformat()}


@router.delete("/freeze-windows/{window_id}")
async def delete_freeze_window_endpoint(window_id: str, tenant_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await delete_freeze_window(db, tenant_id, window_id)
    if not deleted:
        raise HTTPException(404, "Freeze window not found")
    return {"deleted": True}


@router.get("/freeze-status")
async def check_freeze_status(tenant_id: str, db: AsyncSession = Depends(get_db)):
    return await is_frozen(db, tenant_id)


# ── Rollback Policies ──
@router.get("/rollback-policies")
async def get_rollback_policy_endpoint(tenant_id: str, db: AsyncSession = Depends(get_db)):
    policy = await get_rollback_policy(db, tenant_id)
    if not policy:
        return {"rules": [], "enabled": False}
    return {"id": policy.id, "rules": policy.rules_json, "enabled": policy.enabled}


@router.put("/rollback-policies")
async def save_rollback_policy_endpoint(req: SaveRollbackPolicyRequest, db: AsyncSession = Depends(get_db)):
    policy = await save_rollback_policy(db, req.tenant_id, req.rules, req.enabled)
    return {"id": policy.id, "rules": policy.rules_json, "enabled": policy.enabled}
