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
from sqlalchemy import select, desc, func, and_

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

    # Auto-expire scans stuck for more than 10 minutes
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    active_statuses = ["queued", "collecting_data", "analyzing",
                       "generating_recommendations", "building_projections",
                       "running_creative_audit"]
    stale_result = await db.execute(
        select(OperatorScan).where(
            OperatorScan.account_id == req.account_id,
            OperatorScan.status.in_(active_statuses),
            OperatorScan.created_at < stale_cutoff,
        )
    )
    for stale_scan in stale_result.scalars().all():
        stale_scan.status = "failed"
        stale_scan.error_message = "Auto-expired: stuck for >10 minutes"
    await db.commit()

    # Check for duplicate active scans
    existing = await db.execute(
        select(OperatorScan).where(
            OperatorScan.account_id == req.account_id,
            OperatorScan.status.in_(active_statuses),
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


# ── GET /change-set/{id}/status — poll apply + sync progress ─────────────────

@router.get("/change-set/{change_set_id}/status")
async def get_change_set_status(
    change_set_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    cs = await db.get(OperatorChangeSet, change_set_id)
    if not cs or str(cs.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Change set not found")

    # Get account sync status
    account = await db.get(IntegrationGoogleAds, str(cs.account_id))
    sync_status = "idle"
    sync_progress = 0
    sync_message = None
    if account:
        sync_status = getattr(account, "sync_status", "idle") or "idle"
        sync_progress = getattr(account, "sync_progress", 0) or 0
        sync_message = getattr(account, "sync_message", None)

    # Determine overall phase
    # applying → applied (then sync starts) → syncing → done
    if cs.status == "applying":
        phase = "applying"
        overall_progress = 25
    elif cs.status in ("applied", "partially_applied"):
        if sync_status == "syncing":
            phase = "syncing"
            overall_progress = 50 + int(sync_progress * 0.5)
        elif sync_status == "idle" and account and account.last_sync_at and cs.applied_at:
            # Sync completed after apply
            if account.last_sync_at > cs.applied_at:
                phase = "complete"
                overall_progress = 100
            else:
                phase = "waiting_sync"
                overall_progress = 50
        else:
            phase = "waiting_sync"
            overall_progress = 50
    elif cs.status == "failed":
        phase = "failed"
        overall_progress = 0
    else:
        phase = cs.status
        overall_progress = 100

    return {
        "change_set_id": cs.id,
        "change_set_status": cs.status,
        "apply_summary": cs.apply_summary_json,
        "error_message": cs.error_message,
        "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
        "phase": phase,
        "overall_progress": overall_progress,
        "sync_status": sync_status,
        "sync_progress": sync_progress,
        "sync_message": sync_message,
    }


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


# ═══════════════════════════════════════════════════════════════════════════════
# AUTONOMOUS OPTIMIZATION ENGINE — Live Dashboard Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/live/status")
async def get_live_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get the current autonomous optimization status for the tenant."""
    from app.models.v2.optimization_cycle import OptimizationCycle
    from app.models.tenant import Tenant

    tenant = await db.get(Tenant, str(user.tenant_id))

    # Get latest cycle
    result = await db.execute(
        select(OptimizationCycle)
        .where(OptimizationCycle.tenant_id == str(user.tenant_id))
        .order_by(desc(OptimizationCycle.started_at))
        .limit(1)
    )
    latest_cycle = result.scalar_one_or_none()

    # Get stats for last 7 days
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    stats_result = await db.execute(
        select(
            func.count(OptimizationCycle.id).label("total_cycles"),
            func.sum(OptimizationCycle.actions_executed).label("total_executed"),
            func.sum(OptimizationCycle.actions_blocked).label("total_blocked"),
            func.sum(OptimizationCycle.projected_monthly_savings).label("total_savings"),
        ).where(
            and_(
                OptimizationCycle.tenant_id == str(user.tenant_id),
                OptimizationCycle.started_at >= week_ago,
            )
        )
    )
    stats = stats_result.one()

    return {
        "autonomy_mode": tenant.autonomy_mode if tenant else "suggest",
        "risk_tolerance": tenant.risk_tolerance if tenant else "low",
        "latest_cycle": {
            "id": latest_cycle.id,
            "status": latest_cycle.status,
            "trigger": latest_cycle.trigger,
            "problems_detected": latest_cycle.problems_detected,
            "actions_executed": latest_cycle.actions_executed,
            "actions_blocked": latest_cycle.actions_blocked,
            "projected_savings": latest_cycle.projected_monthly_savings,
            "feedback_status": latest_cycle.feedback_status,
            "started_at": latest_cycle.started_at.isoformat() if latest_cycle.started_at else None,
            "completed_at": latest_cycle.completed_at.isoformat() if latest_cycle.completed_at else None,
        } if latest_cycle else None,
        "week_stats": {
            "total_cycles": stats.total_cycles or 0,
            "total_actions_executed": stats.total_executed or 0,
            "total_actions_blocked": stats.total_blocked or 0,
            "projected_monthly_savings": round(float(stats.total_savings or 0), 2),
        },
    }


@router.get("/live/cycles")
async def list_cycles(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, le=100),
):
    """List recent autonomous optimization cycles."""
    from app.models.v2.optimization_cycle import OptimizationCycle

    result = await db.execute(
        select(OptimizationCycle)
        .where(OptimizationCycle.tenant_id == str(user.tenant_id))
        .order_by(desc(OptimizationCycle.started_at))
        .limit(limit)
    )
    cycles = list(result.scalars().all())

    return [
        {
            "id": c.id,
            "trigger": c.trigger,
            "status": c.status,
            "problems_detected": c.problems_detected,
            "actions_generated": c.actions_generated,
            "actions_approved": c.actions_approved,
            "actions_executed": c.actions_executed,
            "actions_blocked": c.actions_blocked,
            "projected_monthly_savings": c.projected_monthly_savings,
            "projected_conversion_lift": c.projected_conversion_lift,
            "feedback_status": c.feedback_status,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        }
        for c in cycles
    ]


@router.get("/live/cycle/{cycle_id}")
async def get_cycle_detail(
    cycle_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get full detail of a specific optimization cycle."""
    from app.models.v2.optimization_cycle import OptimizationCycle

    cycle = await db.get(OptimizationCycle, cycle_id)
    if not cycle or str(cycle.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Cycle not found")

    return {
        "id": cycle.id,
        "trigger": cycle.trigger,
        "status": cycle.status,
        "snapshot": cycle.snapshot_json,
        "problems": cycle.problems_json,
        "actions": cycle.actions_json,
        "problems_detected": cycle.problems_detected,
        "actions_generated": cycle.actions_generated,
        "actions_approved": cycle.actions_approved,
        "actions_executed": cycle.actions_executed,
        "actions_blocked": cycle.actions_blocked,
        "projected_monthly_savings": cycle.projected_monthly_savings,
        "projected_conversion_lift": cycle.projected_conversion_lift,
        "feedback_status": cycle.feedback_status,
        "feedback": cycle.feedback_json,
        "feedback_evaluated_at": cycle.feedback_evaluated_at.isoformat() if cycle.feedback_evaluated_at else None,
        "scan_id": cycle.scan_id,
        "change_set_id": cycle.change_set_id,
        "error_message": cycle.error_message,
        "started_at": cycle.started_at.isoformat() if cycle.started_at else None,
        "completed_at": cycle.completed_at.isoformat() if cycle.completed_at else None,
    }


@router.post("/live/trigger")
async def trigger_manual_cycle(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an autonomous optimization cycle."""
    # Find the first active integration for this tenant
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.tenant_id == str(user.tenant_id),
                IntegrationGoogleAds.customer_id != "pending",
            )
        ).limit(1)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(400, "No connected Google Ads account found")

    from app.jobs.operator_tasks import run_autonomous_cycle_task
    run_autonomous_cycle_task.delay(
        str(user.tenant_id),
        str(integration.id),
        "manual",
    )

    return {"status": "queued", "message": "Optimization cycle triggered"}


@router.post("/live/cycle/{cycle_id}/rollback")
async def rollback_cycle_endpoint(
    cycle_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Rollback all changes from an optimization cycle."""
    from app.models.v2.optimization_cycle import OptimizationCycle

    cycle = await db.get(OptimizationCycle, cycle_id)
    if not cycle or str(cycle.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Cycle not found")
    if cycle.status != "completed" and cycle.feedback_status != "degraded":
        raise HTTPException(400, "Cycle is not eligible for rollback")
    if not cycle.change_set_id:
        raise HTTPException(400, "No change set to rollback")

    from app.jobs.operator_tasks import rollback_cycle_task
    rollback_cycle_task.delay(cycle_id)

    return {"status": "queued", "message": "Rollback initiated"}


@router.get("/live/learnings")
async def get_learnings(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    """Get optimization learnings for the tenant."""
    from app.models.v2.optimization_learning import OptimizationLearning

    result = await db.execute(
        select(OptimizationLearning)
        .where(OptimizationLearning.tenant_id == str(user.tenant_id))
        .order_by(desc(OptimizationLearning.updated_at))
        .limit(limit)
    )
    learnings = list(result.scalars().all())

    return [
        {
            "id": l.id,
            "pattern": l.pattern,
            "action_type": l.action_type,
            "result": l.result,
            "confidence_score": l.confidence_score,
            "observation_count": l.observation_count,
            "pattern_detail": l.pattern_detail_json,
            "result_detail": l.result_detail_json,
            "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        }
        for l in learnings
    ]


# ── Diag: force-clear stuck scans ────────────────────────────────────────────

@router.post("/diag/clear-stuck-scans")
async def diag_clear_stuck_scans(
    key: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Force-expire all active (non-terminal) scans. Requires admin key."""
    if key != "gads2026diag":
        raise HTTPException(403, "Invalid key")

    active_statuses = ["queued", "collecting_data", "analyzing",
                       "generating_recommendations", "building_projections",
                       "running_creative_audit"]
    result = await db.execute(
        select(OperatorScan).where(OperatorScan.status.in_(active_statuses))
    )
    cleared = 0
    for scan in result.scalars().all():
        scan.status = "failed"
        scan.error_message = "Force-cleared via diag endpoint"
        cleared += 1
    await db.commit()
    return {"cleared": cleared}


# ═══════════════════════════════════════════════════════════════════════════════
#  Budget Auto-Scaler
# ═══════════════════════════════════════════════════════════════════════════════


class BudgetScaleRequest(BaseModel):
    account_id: str
    campaign_id: str
    target_cpa: Optional[float] = None  # Dollars


@router.post("/budget-scaler/evaluate")
async def evaluate_budget(
    req: BudgetScaleRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a campaign for ROAS-based budget scaling."""
    integration = await db.get(IntegrationGoogleAds, req.account_id)
    if not integration or str(integration.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Account not found")

    from app.core.security import decrypt_token
    from app.integrations.google_ads.client import GoogleAdsClient
    from app.services.operator.budget_auto_scaler import BudgetAutoScaler
    from app.models.tenant import Tenant

    ads_client = GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token=decrypt_token(integration.encrypted_refresh_token),
    )

    # Load guardrails from tenant
    tenant = await db.get(Tenant, str(user.tenant_id))
    guardrails = {}
    if tenant and hasattr(tenant, "guardrails_json"):
        guardrails = tenant.guardrails_json or {}

    scaler = BudgetAutoScaler(db, str(user.tenant_id), ads_client)
    target_cpa_micros = int(req.target_cpa * 1_000_000) if req.target_cpa else 0

    result = await scaler.evaluate_and_scale(
        campaign_id=req.campaign_id,
        target_cpa_micros=target_cpa_micros,
        guardrails=guardrails,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  A/B Ad Variation Generator
# ═══════════════════════════════════════════════════════════════════════════════


class ABGenerateRequest(BaseModel):
    account_id: str
    campaign_id: str


@router.post("/ab-generator/generate")
async def generate_ab_variations(
    req: ABGenerateRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate A/B ad copy variations for a campaign."""
    integration = await db.get(IntegrationGoogleAds, req.account_id)
    if not integration or str(integration.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Account not found")

    from app.core.security import decrypt_token
    from app.integrations.google_ads.client import GoogleAdsClient
    from app.services.operator.ab_ad_generator import ABAdGenerator

    ads_client = GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token=decrypt_token(integration.encrypted_refresh_token),
    )

    generator = ABAdGenerator(db, str(user.tenant_id), ads_client)
    result = await generator.generate_variations(
        campaign_id=req.campaign_id,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Pipeline Execution Logs (for developer/analyst review)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/logs")
async def get_pipeline_logs(
    service_type: Optional[str] = Query(None, description="Filter: campaign_pipeline, budget_scaler, ab_generator, post_audit, feedback_eval"),
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List pipeline execution logs for the tenant."""
    from app.models.pipeline_execution_log import PipelineExecutionLog

    query = (
        select(PipelineExecutionLog)
        .where(PipelineExecutionLog.tenant_id == str(user.tenant_id))
        .order_by(desc(PipelineExecutionLog.started_at))
        .limit(limit)
    )

    if service_type:
        query = query.where(PipelineExecutionLog.service_type == service_type)
    if campaign_id:
        query = query.where(PipelineExecutionLog.campaign_id == campaign_id)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "service_type": log.service_type,
            "status": log.status,
            "campaign_id": log.campaign_id,
            "conversation_id": log.conversation_id,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_seconds": log.duration_seconds,
            "model_used": log.model_used,
            "input_summary": log.input_summary,
            "output_summary": log.output_summary,
            "ahrefs_data": log.ahrefs_data,
            "agent_results": log.agent_results,
            "error_message": log.error_message,
        }
        for log in logs
    ]


@router.get("/logs/{log_id}")
async def get_pipeline_log_detail(
    log_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get full pipeline execution log detail (including full output)."""
    from app.models.pipeline_execution_log import PipelineExecutionLog

    log = await db.get(PipelineExecutionLog, log_id)
    if not log or str(log.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Log not found")

    return {
        "id": log.id,
        "service_type": log.service_type,
        "status": log.status,
        "campaign_id": log.campaign_id,
        "conversation_id": log.conversation_id,
        "customer_id": log.customer_id,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        "duration_seconds": log.duration_seconds,
        "model_used": log.model_used,
        "total_tokens": log.total_tokens,
        "total_cost_cents": log.total_cost_cents,
        "input_summary": log.input_summary,
        "output_summary": log.output_summary,
        "output_full": log.output_full,
        "ahrefs_data": log.ahrefs_data,
        "agent_results": log.agent_results,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Revenue Attribution — IntelliDrive
# ═══════════════════════════════════════════════════════════════════════════════


class ConversionEventRequest(BaseModel):
    event_type: str = Field(..., description="call, form_submit, booking, walk_in")
    caller_phone: Optional[str] = None
    lead_name: Optional[str] = None
    lead_email: Optional[str] = None
    campaign_id: Optional[str] = None
    keyword_text: Optional[str] = None
    click_id: Optional[str] = None  # gclid


class LinkRevenueRequest(BaseModel):
    conversion_id: str
    job_id: str
    invoice_amount: float  # Dollars
    invoice_date: Optional[str] = None  # YYYY-MM-DD


@router.post("/revenue/conversion")
async def record_conversion(
    req: ConversionEventRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Record a conversion event (call, form, booking) and optionally link to Google Ads."""
    from app.services.operator.revenue_attribution import RevenueAttributionService

    svc = RevenueAttributionService(db, str(user.tenant_id))
    result = await svc.record_conversion_event(
        event_type=req.event_type,
        source_data={
            "caller_phone": req.caller_phone,
            "lead_name": req.lead_name,
            "lead_email": req.lead_email,
        },
    )
    # Link to campaign if provided
    if req.campaign_id and result.get("conversion_id"):
        await svc.link_to_campaign(
            conversion_id=result["conversion_id"],
            campaign_id=req.campaign_id,
            keyword_text=req.keyword_text,
            click_id=req.click_id,
        )
    await db.commit()
    return result


@router.post("/revenue/link-job")
async def link_job_revenue(
    req: LinkRevenueRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Link actual job revenue to a conversion event for true ROAS."""
    from app.services.operator.revenue_attribution import RevenueAttributionService
    from datetime import date as dt_date

    invoice_date = None
    if req.invoice_date:
        invoice_date = dt_date.fromisoformat(req.invoice_date)

    svc = RevenueAttributionService(db, str(user.tenant_id))
    result = await svc.record_job_revenue(
        conversion_id=req.conversion_id,
        job_id=req.job_id,
        invoice_amount=req.invoice_amount,
        invoice_date=invoice_date,
    )
    await db.commit()
    return result


@router.get("/revenue/true-roas/{campaign_id}")
async def get_true_roas(
    campaign_id: str,
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get true ROAS for a campaign based on actual invoice revenue vs ad spend."""
    from app.services.operator.revenue_attribution import RevenueAttributionService

    svc = RevenueAttributionService(db, str(user.tenant_id))
    return await svc.get_true_roas(campaign_id, days)


@router.get("/revenue/report")
async def get_attribution_report(
    days: int = Query(30, ge=7, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Full revenue attribution report: spend, clicks, calls, jobs, revenue per campaign."""
    from app.services.operator.revenue_attribution import RevenueAttributionService

    svc = RevenueAttributionService(db, str(user.tenant_id))
    return await svc.get_attribution_report(str(user.tenant_id), days)


@router.get("/revenue/top-keywords")
async def get_top_revenue_keywords(
    limit: int = Query(20, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Keywords ranked by actual revenue generated (not just conversions)."""
    from app.services.operator.revenue_attribution import RevenueAttributionService

    svc = RevenueAttributionService(db, str(user.tenant_id))
    return await svc.get_top_revenue_keywords(str(user.tenant_id), limit)


# ═══════════════════════════════════════════════════════════════════════════════
#  Pipeline A/B Variant Tracking
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/pipeline/ab-variants")
async def get_ab_variants(
    limit: int = Query(50, le=200),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get pipeline A/B variant history with performance data."""
    from app.services.operator.pipeline_ab_tracker import PipelineABTracker

    tracker = PipelineABTracker(db)
    winning = await tracker.get_winning_variants(str(user.tenant_id))
    return winning


@router.get("/pipeline/feedback")
async def get_pipeline_feedback(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get performance feedback learnings for this tenant's pipeline runs."""
    from app.services.operator.performance_feedback_service import PerformanceFeedbackService

    svc = PerformanceFeedbackService(db, str(user.tenant_id))
    return await svc.get_pipeline_learnings()


# ═══════════════════════════════════════════════════════════════════════════════
#  Landing Page Agent — edit, regenerate, approve, generate images
# ═══════════════════════════════════════════════════════════════════════════════


class LPEditRequest(BaseModel):
    landing_page_id: str
    variant_key: str  # A, B, C
    edit_prompt: str  # "change the headline to...", "add testimonials", "make it more urgent"
    conversation_id: Optional[str] = None


class LPApproveRequest(BaseModel):
    landing_page_id: str
    variant_key: str  # A, B, C
    conversation_id: Optional[str] = None


class LPRegenerateRequest(BaseModel):
    landing_page_id: str
    variant_key: str
    angle: Optional[str] = None  # "urgent", "premium", "price", "trust"
    conversation_id: Optional[str] = None


@router.post("/landing-page/edit")
async def edit_landing_page_variant(
    req: LPEditRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Apply a prompt-based edit to a landing page variant (AI-powered)."""
    from app.services.operator.landing_page_agent import LandingPageAgent

    agent = LandingPageAgent(db, str(user.tenant_id))
    result = await agent.edit_variant(
        landing_page_id=req.landing_page_id,
        variant_key=req.variant_key,
        edit_prompt=req.edit_prompt,
        conversation_id=req.conversation_id or "",
    )
    if result.get("error"):
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/landing-page/approve")
async def approve_landing_page_variant(
    req: LPApproveRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve a landing page variant — publishes it and audits quality."""
    from app.services.operator.landing_page_agent import LandingPageAgent

    agent = LandingPageAgent(db, str(user.tenant_id))
    result = await agent.approve_variant(
        landing_page_id=req.landing_page_id,
        variant_key=req.variant_key,
        campaign_spec={},  # Will be linked when campaign is deployed
    )
    if result.get("error"):
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/landing-page/regenerate")
async def regenerate_landing_page_variant(
    req: LPRegenerateRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate a landing page variant with a new angle."""
    from app.services.operator.landing_page_agent import LandingPageAgent

    agent = LandingPageAgent(db, str(user.tenant_id))
    result = await agent.regenerate_variant(
        landing_page_id=req.landing_page_id,
        variant_key=req.variant_key,
        new_angle=req.angle or "",
        conversation_id=req.conversation_id or "",
    )
    if result.get("error"):
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.post("/landing-page/{landing_page_id}/generate-images")
async def generate_landing_page_images(
    landing_page_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI hero images for all variants of a landing page."""
    from app.services.operator.landing_page_agent import LandingPageAgent

    agent = LandingPageAgent(db, str(user.tenant_id))
    result = await agent.generate_images(landing_page_id=landing_page_id)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    await db.commit()
    return result


@router.get("/landing-page/{landing_page_id}/preview/{variant_key}")
async def preview_landing_page(
    landing_page_id: str,
    variant_key: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get HTML preview of a landing page variant."""
    from app.models.landing_page import LandingPage
    from app.services.operator.landing_page_agent import LandingPageAgent

    lp = await db.get(LandingPage, landing_page_id)
    if not lp or str(lp.tenant_id) != str(user.tenant_id):
        raise HTTPException(404, "Landing page not found")

    agent = LandingPageAgent(db, str(user.tenant_id))
    biz_ctx = await agent._get_business_context()

    variant_content = {}
    for v in (lp.variants or []):
        if v.variant_key == variant_key.upper():
            variant_content = v.content_json
            break

    if not variant_content:
        raise HTTPException(404, f"Variant {variant_key} not found")

    html = agent._render_preview_html(variant_content, biz_ctx, lp.strategy_json or {})
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


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
