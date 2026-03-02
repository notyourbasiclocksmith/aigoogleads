"""
Module 3 — Advanced Change Management (DevOps-style)
Change sets, scheduled apply, freeze windows, automatic rollback triggers, canary changes.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from app.models.v2.change_set import ChangeSet
from app.models.v2.change_set_item import ChangeSetItem
from app.models.v2.freeze_window import FreezeWindow
from app.models.v2.rollback_policy import RollbackPolicy
from app.models.change_log import ChangeLog

logger = structlog.get_logger()


# ── Freeze Window Checks ──
async def is_frozen(db: AsyncSession, tenant_id: str, at_time: Optional[datetime] = None) -> Dict[str, Any]:
    """Check if tenant is in a freeze window."""
    now = at_time or datetime.now(timezone.utc)
    stmt = select(FreezeWindow).where(
        and_(
            FreezeWindow.tenant_id == tenant_id,
            FreezeWindow.start_at <= now,
            FreezeWindow.end_at >= now,
        )
    )
    result = await db.execute(stmt)
    window = result.scalars().first()
    if window:
        return {"frozen": True, "reason": window.reason, "ends_at": window.end_at.isoformat()}
    return {"frozen": False}


async def get_freeze_windows(db: AsyncSession, tenant_id: str) -> List[FreezeWindow]:
    stmt = select(FreezeWindow).where(FreezeWindow.tenant_id == tenant_id).order_by(FreezeWindow.start_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_freeze_window(
    db: AsyncSession, tenant_id: str, start_at: datetime, end_at: datetime, reason: str
) -> FreezeWindow:
    window = FreezeWindow(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        start_at=start_at,
        end_at=end_at,
        reason=reason,
    )
    db.add(window)
    return window


async def delete_freeze_window(db: AsyncSession, tenant_id: str, window_id: str) -> bool:
    stmt = select(FreezeWindow).where(
        and_(FreezeWindow.id == window_id, FreezeWindow.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    window = result.scalars().first()
    if window:
        await db.delete(window)
        return True
    return False


# ── Change Sets ──
async def create_change_set(
    db: AsyncSession, tenant_id: str, name: str, change_log_ids: List[str],
    scheduled_for: Optional[datetime] = None, created_by: Optional[str] = None,
) -> ChangeSet:
    """Create a change set grouping multiple change log entries."""
    status = "scheduled" if scheduled_for else "draft"
    cs = ChangeSet(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        status=status,
        scheduled_for=scheduled_for,
        created_by=created_by,
    )
    db.add(cs)

    # Add items with ordering: negatives(0) → bids(1) → budgets(2) → ads(3)
    CATEGORY_ORDER = {"negative": 0, "bid": 1, "budget": 2, "ad": 3, "keyword": 1, "other": 4}
    items_with_order = []
    for cl_id in change_log_ids:
        cl_stmt = select(ChangeLog).where(ChangeLog.id == cl_id)
        cl_result = await db.execute(cl_stmt)
        cl = cl_result.scalars().first()
        category = "other"
        if cl and cl.entity_type:
            et = cl.entity_type.lower()
            for key in CATEGORY_ORDER:
                if key in et:
                    category = key
                    break
        items_with_order.append((cl_id, CATEGORY_ORDER.get(category, 4)))

    items_with_order.sort(key=lambda x: x[1])
    for idx, (cl_id, _) in enumerate(items_with_order):
        item = ChangeSetItem(
            id=str(uuid.uuid4()),
            change_set_id=cs.id,
            change_log_id=cl_id,
            apply_order=idx,
        )
        db.add(item)

    return cs


async def get_change_sets(db: AsyncSession, tenant_id: str) -> List[ChangeSet]:
    stmt = select(ChangeSet).where(ChangeSet.tenant_id == tenant_id).order_by(ChangeSet.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def apply_change_set(db: AsyncSession, tenant_id: str, change_set_id: str) -> Dict[str, Any]:
    """Apply a change set. Check freeze windows first."""
    freeze_check = await is_frozen(db, tenant_id)
    if freeze_check["frozen"]:
        return {"applied": False, "error": f"Tenant is in freeze window: {freeze_check['reason']}"}

    stmt = select(ChangeSet).where(
        and_(ChangeSet.id == change_set_id, ChangeSet.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    cs = result.scalars().first()
    if not cs:
        return {"applied": False, "error": "Change set not found"}
    if cs.status not in ("draft", "scheduled"):
        return {"applied": False, "error": f"Change set status is '{cs.status}', cannot apply"}

    cs.status = "applying"
    # In production, each item's change_log would be applied via Google Ads API in order
    # For now, mark as applied
    cs.status = "applied"
    cs.applied_at = datetime.now(timezone.utc)
    logger.info("Change set applied", change_set_id=cs.id, tenant_id=tenant_id)
    return {"applied": True, "change_set_id": cs.id, "items_count": len(cs.items)}


async def rollback_change_set(db: AsyncSession, tenant_id: str, change_set_id: str) -> Dict[str, Any]:
    """Rollback a previously applied change set."""
    stmt = select(ChangeSet).where(
        and_(ChangeSet.id == change_set_id, ChangeSet.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    cs = result.scalars().first()
    if not cs:
        return {"rolled_back": False, "error": "Change set not found"}
    if cs.status != "applied":
        return {"rolled_back": False, "error": f"Change set status is '{cs.status}', cannot rollback"}

    # In production, reverse each item in reverse order via Google Ads API
    cs.status = "rolled_back"
    cs.rolled_back_at = datetime.now(timezone.utc)
    logger.info("Change set rolled back", change_set_id=cs.id, tenant_id=tenant_id)
    return {"rolled_back": True, "change_set_id": cs.id}


# ── Scheduled Changes ──
async def get_due_scheduled_sets(db: AsyncSession) -> List[ChangeSet]:
    """Get all change sets that are scheduled and past due."""
    now = datetime.now(timezone.utc)
    stmt = select(ChangeSet).where(
        and_(
            ChangeSet.status == "scheduled",
            ChangeSet.scheduled_for <= now,
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ── Rollback Policies / Triggers ──
async def get_rollback_policy(db: AsyncSession, tenant_id: str) -> Optional[RollbackPolicy]:
    stmt = select(RollbackPolicy).where(
        and_(RollbackPolicy.tenant_id == tenant_id, RollbackPolicy.enabled == True)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def save_rollback_policy(db: AsyncSession, tenant_id: str, rules: list, enabled: bool = True) -> RollbackPolicy:
    policy = await get_rollback_policy(db, tenant_id)
    if policy:
        policy.rules_json = rules
        policy.enabled = enabled
        policy.updated_at = datetime.now(timezone.utc)
    else:
        policy = RollbackPolicy(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            rules_json=rules,
            enabled=enabled,
        )
        db.add(policy)
    return policy


async def evaluate_rollback_triggers(
    db: AsyncSession,
    tenant_id: str,
    current_metrics: Dict[str, float],
    baseline_metrics: Dict[str, float],
) -> Dict[str, Any]:
    """
    Evaluate rollback trigger rules against current vs baseline metrics.
    Rules format: [
        {"metric": "conversions", "condition": "drop_pct", "threshold": 20, "window_days": 3},
        {"metric": "cpa", "condition": "increase_pct", "threshold": 30, "window_days": 3},
        {"metric": "spend", "condition": "spike_pct", "threshold": 50, "window_days": 1},
    ]
    """
    policy = await get_rollback_policy(db, tenant_id)
    if not policy or not policy.rules_json:
        return {"triggered": False, "violations": []}

    violations = []
    for rule in policy.rules_json:
        metric = rule.get("metric", "")
        condition = rule.get("condition", "")
        threshold = rule.get("threshold", 0)
        current_val = current_metrics.get(metric, 0)
        baseline_val = baseline_metrics.get(metric, 0)

        if baseline_val == 0:
            continue

        pct_change = ((current_val - baseline_val) / abs(baseline_val)) * 100

        triggered = False
        if condition == "drop_pct" and pct_change < -abs(threshold):
            triggered = True
        elif condition == "increase_pct" and pct_change > abs(threshold):
            triggered = True
        elif condition == "spike_pct" and pct_change > abs(threshold):
            triggered = True

        if triggered:
            violations.append({
                "rule": rule,
                "current": current_val,
                "baseline": baseline_val,
                "pct_change": round(pct_change, 2),
            })

    return {
        "triggered": len(violations) > 0,
        "violations": violations,
    }
