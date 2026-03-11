"""
AI Campaign Operator API — v2 endpoints for scan, recommendations,
change sets, and mutations.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.v2.operator_scan import OperatorScan
from app.models.v2.operator_recommendation import OperatorRecommendation
from app.models.v2.operator_change_set import OperatorChangeSet
from app.models.v2.operator_mutation import OperatorMutation
from app.models import IntegrationGoogleAds

router = APIRouter()


# ── Request / Response schemas ───────────────────────────────────────────────

class ScanRequest(BaseModel):
    account_id: str
    date_range: str = "30d"  # 7d, 14d, 30d, or "YYYY-MM-DD:YYYY-MM-DD"
    campaign_ids: Optional[List[str]] = None
    scan_goal: str = "full_review"  # reduce_waste, increase_conversions, improve_cpa, scale_winners, full_review


class ChangeSetRequest(BaseModel):
    scan_id: str
    selected_recommendation_ids: List[str]
    edited_overrides: Optional[dict] = None


class ScanStatusResponse(BaseModel):
    scan_id: str
    status: str


# ── POST /scan — start a new operator scan ───────────────────────────────────

@router.post("/scan")
async def start_scan(
    req: ScanRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Validate account belongs to tenant
    integration = await db.get(IntegrationGoogleAds, req.account_id)
    if not integration or str(integration.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Account not found")
    if integration.customer_id == "pending":
        raise HTTPException(400, "Google Ads account not fully connected yet")

    # Parse date range
    date_start, date_end = _parse_date_range(req.date_range)

    # Check for duplicate active scans
    existing = await db.execute(
        select(OperatorScan).where(
            OperatorScan.account_id == req.account_id,
            OperatorScan.status.in_(["queued", "collecting_data", "analyzing",
                                      "generating_recommendations", "building_projections",
                                      "running_creative_audit"]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "A scan is already running for this account")

    scan = OperatorScan(
        id=str(uuid.uuid4()),
        tenant_id=str(user.tenant_id),
        account_id=req.account_id,
        requested_by=str(user.user_id),
        date_range_start=date_start,
        date_range_end=date_end,
        scan_goal=req.scan_goal,
        campaign_scope="selected" if req.campaign_ids else "all",
        campaign_ids_json=req.campaign_ids or [],
        status="queued",
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    # Queue Celery task
    from app.jobs.operator_tasks import run_operator_scan_task
    run_operator_scan_task.delay(scan.id)

    return {"scan_id": scan.id, "status": "queued"}


# ── GET /scan/{scan_id} — full scan result ───────────────────────────────────

@router.get("/scan/{scan_id}")
async def get_scan(
    scan_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.services.operator.operator_orchestrator import get_scan_result
    result = await get_scan_result(scan_id, db)
    if not result:
        raise HTTPException(404, "Scan not found")
    return result


# ── GET /scan/{scan_id}/status — poll scan status ────────────────────────────

@router.get("/scan/{scan_id}/status")
async def get_scan_status(
    scan_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    scan = await db.get(OperatorScan, scan_id)
    if not scan or str(scan.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Scan not found")
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "error_message": scan.error_message,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }


# ── GET /scan/{scan_id}/recommendations ──────────────────────────────────────

@router.get("/scan/{scan_id}/recommendations")
async def get_recommendations(
    scan_id: str,
    group: Optional[str] = Query(None),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(OperatorRecommendation).where(
        OperatorRecommendation.scan_id == scan_id
    ).order_by(OperatorRecommendation.priority_order)

    if group:
        query = query.where(OperatorRecommendation.group_name == group)

    result = await db.execute(query)
    recs = list(result.scalars().all())

    return [
        {
            "id": r.id,
            "type": r.recommendation_type,
            "group": r.group_name,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "entity_name": r.entity_name,
            "title": r.title,
            "rationale": r.rationale,
            "evidence": r.evidence_json,
            "current_state": r.current_state_json,
            "proposed_state": r.proposed_state_json,
            "confidence": r.confidence_score,
            "risk_level": r.risk_level,
            "impact": r.impact_projection_json,
            "generated_by": r.generated_by,
            "status": r.status,
            "priority": r.priority_order,
        }
        for r in recs
    ]


# ── GET /scan/{scan_id}/projections ──────────────────────────────────────────

@router.get("/scan/{scan_id}/projections")
async def get_projections(
    scan_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    scan = await db.get(OperatorScan, scan_id)
    if not scan or str(scan.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Scan not found")
    return scan.summary_json or {}


# ── GET /scan/{scan_id}/creative-audit ───────────────────────────────────────

@router.get("/scan/{scan_id}/creative-audit")
async def get_creative_audit(
    scan_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.models.v2.creative_audit import CreativeAudit
    result = await db.execute(
        select(CreativeAudit).where(CreativeAudit.scan_id == scan_id)
    )
    audits = list(result.scalars().all())
    return [
        {
            "entity_name": a.entity_name,
            "copy_audit": a.copy_audit_json,
            "asset_audit": a.asset_audit_json,
            "image_prompts": a.image_prompt_pack_json,
            "generated_creatives": a.generated_creatives_json,
        }
        for a in audits
    ]


# ── POST /change-set — create change set from selected recommendations ──────

@router.post("/change-set")
async def create_change_set_endpoint(
    req: ChangeSetRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.services.operator.operator_orchestrator import create_change_set
    try:
        cs = await create_change_set(
            scan_id=req.scan_id,
            selected_recommendation_ids=req.selected_recommendation_ids,
            approved_by=str(user.user_id),
            db=db,
            edited_overrides=req.edited_overrides,
        )
        return {
            "change_set_id": cs.id,
            "status": cs.status,
            "selected_count": len(req.selected_recommendation_ids),
            "projection": cs.projection_summary_json,
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── GET /change-set/{id} — get change set detail ────────────────────────────

@router.get("/change-set/{change_set_id}")
async def get_change_set(
    change_set_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(OperatorChangeSet, change_set_id)
    if not cs or str(cs.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Change set not found")
    return {
        "id": cs.id,
        "scan_id": cs.scan_id,
        "status": cs.status,
        "selected_recommendation_ids": cs.selected_recommendation_ids,
        "projection": cs.projection_summary_json,
        "validation": cs.validation_result_json,
        "apply_summary": cs.apply_summary_json,
        "error_message": cs.error_message,
        "created_at": cs.created_at.isoformat() if cs.created_at else None,
        "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
    }


# ── POST /change-set/{id}/validate ──────────────────────────────────────────

@router.post("/change-set/{change_set_id}/validate")
async def validate_change_set(
    change_set_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(OperatorChangeSet, change_set_id)
    if not cs or str(cs.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Change set not found")

    # Check scan staleness (if scan is > 24h old, warn)
    scan = await db.get(OperatorScan, cs.scan_id)
    warnings = []
    if scan and scan.completed_at:
        age = datetime.now(timezone.utc) - scan.completed_at
        if age > timedelta(hours=24):
            warnings.append(f"Scan data is {age.total_seconds()/3600:.0f} hours old — consider re-scanning")

    cs.status = "validated"
    cs.validated_at = datetime.now(timezone.utc)
    cs.validation_result_json = {"valid": True, "warnings": warnings}
    await db.commit()

    return {"valid": True, "warnings": warnings}


# ── POST /change-set/{id}/apply ──────────────────────────────────────────────

@router.post("/change-set/{change_set_id}/apply")
async def apply_change_set(
    change_set_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(OperatorChangeSet, change_set_id)
    if not cs or str(cs.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Change set not found")
    if cs.status not in ("draft", "validated"):
        raise HTTPException(400, f"Change set cannot be applied in status '{cs.status}'")

    cs.status = "applying"
    await db.commit()

    from app.jobs.operator_tasks import apply_change_set_task
    apply_change_set_task.delay(change_set_id)

    return {"change_set_id": cs.id, "status": "applying"}


# ── POST /change-set/{id}/rollback ──────────────────────────────────────────

@router.post("/change-set/{change_set_id}/rollback")
async def rollback_change_set(
    change_set_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(OperatorChangeSet, change_set_id)
    if not cs or str(cs.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Change set not found")
    if cs.status != "applied":
        raise HTTPException(400, "Can only rollback applied change sets")

    # TODO: Execute rollback mutations
    cs.status = "rolled_back"
    cs.rolled_back_at = datetime.now(timezone.utc)
    await db.commit()

    return {"change_set_id": cs.id, "status": "rolled_back"}


# ── GET /history — list past scans ───────────────────────────────────────────

@router.get("/history")
async def list_scan_history(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100),
):
    result = await db.execute(
        select(OperatorScan)
        .where(OperatorScan.tenant_id == str(user.tenant_id))
        .order_by(desc(OperatorScan.created_at))
        .limit(limit)
    )
    scans = list(result.scalars().all())
    return [
        {
            "scan_id": s.id,
            "account_id": s.account_id,
            "status": s.status,
            "scan_goal": s.scan_goal,
            "date_range": f"{s.date_range_start} — {s.date_range_end}",
            "total_recommendations": len(s.recommendations) if s.recommendations else 0,
            "summary": s.summary_json,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in scans
    ]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date_range(date_range: str):
    """Parse '7d', '14d', '30d', or 'YYYY-MM-DD:YYYY-MM-DD'."""
    if ":" in date_range:
        parts = date_range.split(":")
        return parts[0], parts[1]

    days = {"7d": 7, "14d": 14, "30d": 30, "60d": 60, "90d": 90}
    d = days.get(date_range, 30)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=d)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
