"""
Autonomous Optimizer — scheduled optimization loop that runs every 4 hours.

Flow:
1. Collect account snapshot (reuses account_scan_service)
2. Detect problems + generate recommendations (reuses recommendation_engine)
3. Filter by risk level + tenant autonomy mode
4. Auto-execute safe actions via ExecutionEngine
5. Record cycle in OptimizationCycle
6. Queue feedback evaluation for 24h later

Integrates with existing:
- account_scan_service.collect_account_data
- recommendation_engine.generate_recommendations
- projection_engine.build_projections
- guardrails.GuardrailsEngine
- execution_engine.ExecutionEngine
"""
import uuid
import structlog
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.tenant import Tenant
from app.models import IntegrationGoogleAds
from app.models.v2.operator_scan import OperatorScan
from app.models.v2.operator_recommendation import OperatorRecommendation
from app.models.v2.operator_change_set import OperatorChangeSet
from app.models.v2.optimization_cycle import OptimizationCycle
from app.core.security import decrypt_token

from app.services.operator.schemas import (
    RiskLevel, RecommendationOutput, ImpactProjection, RecType, RecGroup,
)
from app.services.operator.account_scan_service import collect_account_data
from app.services.operator.recommendation_engine import generate_recommendations
from app.services.operator.projection_engine import build_projections
from app.services.operator.execution_engine import ExecutionEngine

logger = structlog.get_logger()

# Safety: maximum actions per single autonomous cycle
MAX_AUTO_ACTIONS_PER_CYCLE = 15
# Minimum hours between autonomous cycles for same account
MIN_CYCLE_INTERVAL_HOURS = 3


async def run_autonomous_cycle(
    tenant_id: str,
    account_id: str,
    db: AsyncSession,
    trigger: str = "scheduled",
) -> Dict[str, Any]:
    """
    Run one full autonomous optimization cycle for an account.
    Returns cycle summary.
    """
    cycle = OptimizationCycle(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        account_id=account_id,
        trigger=trigger,
        status="running",
    )
    db.add(cycle)
    await db.commit()

    try:
        # ── Pre-checks ────────────────────────────────────────────────
        tenant = await _get_tenant(db, tenant_id)
        if not tenant:
            cycle.status = "failed"
            cycle.error_message = "Tenant not found"
            await db.commit()
            return {"status": "failed", "error": "Tenant not found"}

        if tenant.autonomy_mode == "suggest":
            cycle.status = "skipped"
            cycle.error_message = "Tenant in suggest-only mode"
            cycle.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "skipped", "reason": "suggest_mode"}

        # Check for recent cycles (prevent overlapping runs)
        if await _has_recent_cycle(db, account_id):
            cycle.status = "skipped"
            cycle.error_message = f"Recent cycle within {MIN_CYCLE_INTERVAL_HOURS}h"
            cycle.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "skipped", "reason": "too_recent"}

        # Check freeze windows
        from app.services.v2.change_management import is_frozen
        freeze = await is_frozen(db, tenant_id)
        if freeze.get("frozen"):
            cycle.status = "skipped"
            cycle.error_message = f"Freeze window active: {freeze.get('reason')}"
            cycle.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "skipped", "reason": "frozen"}

        # Get integration
        integration = await db.get(IntegrationGoogleAds, account_id)
        if not integration or not integration.refresh_token_encrypted:
            cycle.status = "failed"
            cycle.error_message = "No Google Ads integration"
            await db.commit()
            return {"status": "failed", "error": "no_integration"}

        refresh_token = decrypt_token(integration.refresh_token_encrypted)
        customer_id = integration.customer_id
        if not customer_id or customer_id == "pending":
            cycle.status = "failed"
            cycle.error_message = "Customer ID not configured"
            await db.commit()
            return {"status": "failed", "error": "no_customer_id"}

        # ── Step 1: Collect snapshot ───────────────────────────────────
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=30)

        snapshot = await collect_account_data(
            refresh_token=refresh_token,
            customer_id=customer_id,
            date_start=start_date.strftime("%Y-%m-%d"),
            date_end=end_date.strftime("%Y-%m-%d"),
            login_customer_id=integration.login_customer_id,
        )

        cycle.snapshot_json = {
            "total_spend": snapshot.total_spend,
            "total_conversions": snapshot.total_conversions,
            "total_clicks": snapshot.total_clicks,
            "total_impressions": snapshot.total_impressions,
            "campaigns": len(snapshot.campaigns),
            "ad_groups": len(snapshot.ad_groups),
            "keywords": len(snapshot.keywords),
            "search_terms": len(snapshot.search_terms),
            "ads": len(snapshot.ads),
        }

        # ── Step 2: Detect problems + generate recommendations ─────────
        recommendations = await generate_recommendations(snapshot, "full_review")

        problems = []
        for rec in recommendations:
            problems.append({
                "type": rec.recommendation_type.value,
                "entity": rec.entity_name,
                "severity": rec.risk_level.value,
                "title": rec.title,
            })

        cycle.problems_detected = len(recommendations)
        cycle.problems_json = problems
        cycle.actions_generated = len(recommendations)

        if not recommendations:
            cycle.status = "completed_no_actions"
            cycle.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "completed_no_actions", "cycle_id": cycle.id}

        # ── Step 3: Filter by risk + autonomy mode ─────────────────────
        allowed_recs = _filter_by_autonomy(recommendations, tenant)

        cycle.actions_approved = len(allowed_recs)
        cycle.actions_blocked = len(recommendations) - len(allowed_recs)

        if not allowed_recs:
            cycle.status = "completed_no_actions"
            cycle.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Autonomous cycle: all actions blocked by guardrails",
                        tenant_id=tenant_id, total=len(recommendations))
            return {"status": "completed_no_actions", "cycle_id": cycle.id,
                    "reason": "all_blocked_by_guardrails"}

        # Cap actions per cycle
        if len(allowed_recs) > MAX_AUTO_ACTIONS_PER_CYCLE:
            allowed_recs = allowed_recs[:MAX_AUTO_ACTIONS_PER_CYCLE]
            cycle.actions_approved = len(allowed_recs)

        # ── Step 4: Build projections ──────────────────────────────────
        summary = build_projections(snapshot, allowed_recs)

        cycle.projected_monthly_savings = round(
            abs(summary.wasted_spend_estimate) * 30 / 30, 2  # already 30d window
        )
        cycle.projected_conversion_lift = round(
            summary.projected_conversion_lift_high, 1
        )

        # ── Step 5: Create operator scan + change set + execute ────────
        # Create a lightweight OperatorScan to link artifacts
        scan = OperatorScan(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            account_id=account_id,
            date_range_start=start_date.strftime("%Y-%m-%d"),
            date_range_end=end_date.strftime("%Y-%m-%d"),
            scan_goal="full_review",
            campaign_scope="all",
            status="ready",
            metrics_snapshot_json=cycle.snapshot_json,
            summary_json=summary.model_dump(),
            confidence_score=summary.confidence_score,
            risk_score=summary.risk_score,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(scan)
        await db.flush()

        # Persist recommendations
        rec_ids = []
        for rec in allowed_recs:
            db_rec = OperatorRecommendation(
                id=str(uuid.uuid4()),
                scan_id=scan.id,
                tenant_id=tenant_id,
                recommendation_type=rec.recommendation_type.value,
                group_name=rec.group_name.value,
                entity_type=rec.entity_type,
                entity_id=rec.entity_id,
                entity_name=rec.entity_name,
                parent_entity_id=rec.parent_entity_id,
                title=rec.title,
                rationale=rec.rationale,
                evidence_json=rec.evidence,
                current_state_json=rec.current_state,
                proposed_state_json=rec.proposed_state,
                confidence_score=rec.confidence_score,
                risk_level=rec.risk_level.value,
                impact_projection_json=rec.impact.model_dump(),
                generated_by=rec.generated_by,
                priority_order=rec.priority_order,
                status="approved",  # Auto-approved by autonomy filter
            )
            db.add(db_rec)
            rec_ids.append(db_rec.id)

        # Create change set
        cs = OperatorChangeSet(
            id=str(uuid.uuid4()),
            scan_id=scan.id,
            tenant_id=tenant_id,
            account_id=account_id,
            selected_recommendation_ids=rec_ids,
            projection_summary_json=summary.model_dump(),
            status="validated",
            validated_at=datetime.now(timezone.utc),
        )
        db.add(cs)
        await db.flush()

        cycle.scan_id = scan.id
        cycle.change_set_id = cs.id

        # Execute mutations
        engine = ExecutionEngine(db)
        exec_result = await engine.execute_change_set(cs.id)

        cycle.actions_executed = exec_result.get("executed", 0)

        # Build actions log
        actions_log = []
        for rec in allowed_recs:
            actions_log.append({
                "action_type": rec.recommendation_type.value,
                "entity_type": rec.entity_type,
                "entity_id": rec.entity_id,
                "entity_name": rec.entity_name,
                "risk_level": rec.risk_level.value,
                "status": "executed",
                "impact_estimate": {
                    "spend_delta": rec.impact.spend_delta,
                    "conversion_delta": rec.impact.conversion_delta,
                },
            })
        cycle.actions_json = actions_log

        # ── Complete cycle ─────────────────────────────────────────────
        cycle.status = "completed"
        cycle.feedback_status = "pending_review"
        cycle.completed_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info(
            "Autonomous optimization cycle completed",
            tenant_id=tenant_id,
            cycle_id=cycle.id,
            problems=cycle.problems_detected,
            approved=cycle.actions_approved,
            executed=cycle.actions_executed,
            blocked=cycle.actions_blocked,
            projected_savings=cycle.projected_monthly_savings,
        )

        # Queue feedback evaluation for 24h later
        from app.jobs.operator_tasks import evaluate_cycle_feedback_task
        evaluate_cycle_feedback_task.apply_async(
            args=[cycle.id],
            countdown=86400,  # 24 hours
        )

        return {
            "status": "completed",
            "cycle_id": cycle.id,
            "problems_detected": cycle.problems_detected,
            "actions_executed": cycle.actions_executed,
            "actions_blocked": cycle.actions_blocked,
            "projected_monthly_savings": cycle.projected_monthly_savings,
        }

    except Exception as ex:
        logger.error("Autonomous cycle failed",
                     tenant_id=tenant_id, error=str(ex))
        cycle.status = "failed"
        cycle.error_message = str(ex)[:500]
        cycle.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"status": "failed", "error": str(ex)}


def _filter_by_autonomy(
    recommendations: List[RecommendationOutput],
    tenant: Tenant,
) -> List[RecommendationOutput]:
    """
    Filter recommendations based on tenant autonomy mode and risk tolerance.
    Returns only actions that can be auto-executed.
    """
    allowed = []

    for rec in recommendations:
        # In semi_auto: only LOW risk actions
        if tenant.autonomy_mode == "semi_auto":
            if rec.risk_level == RiskLevel.LOW:
                allowed.append(rec)

        # In full_auto: LOW + MEDIUM (unless low risk tolerance)
        elif tenant.autonomy_mode == "full_auto":
            if rec.risk_level == RiskLevel.LOW:
                allowed.append(rec)
            elif rec.risk_level == RiskLevel.MEDIUM:
                if tenant.risk_tolerance in ("medium", "high"):
                    allowed.append(rec)

        # Budget increases always capped
        if rec.recommendation_type in (RecType.INCREASE_BUDGET,):
            # Check budget guardrail
            proposed = rec.proposed_state or {}
            current = rec.current_state or {}
            new_budget = proposed.get("budget_daily", 0)
            old_budget = current.get("budget_daily", 0)
            if old_budget > 0 and new_budget > 0:
                change_pct = ((new_budget - old_budget) / old_budget) * 100
                max_pct = tenant.weekly_change_cap_pct or 20
                if change_pct > max_pct:
                    # Remove from allowed if it was added
                    allowed = [r for r in allowed if r is not rec]

    return allowed


async def _get_tenant(db: AsyncSession, tenant_id: str) -> Optional[Tenant]:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def _has_recent_cycle(db: AsyncSession, account_id: str) -> bool:
    """Check if there's been a cycle in the last MIN_CYCLE_INTERVAL_HOURS hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MIN_CYCLE_INTERVAL_HOURS)
    result = await db.execute(
        select(OptimizationCycle).where(
            OptimizationCycle.account_id == account_id,
            OptimizationCycle.started_at >= cutoff,
            OptimizationCycle.status.in_(["running", "completed"]),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def run_all_accounts(db: AsyncSession) -> Dict[str, Any]:
    """
    Run autonomous optimization for ALL active accounts.
    Called by the periodic Celery beat task.
    """
    # Find all active integrations with connected accounts
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.customer_id != "pending",
            IntegrationGoogleAds.refresh_token_encrypted.isnot(None),
        )
    )
    integrations = list(result.scalars().all())

    results = []
    for integration in integrations:
        tenant_id = str(integration.tenant_id)

        # Check tenant has autopilot enabled
        tenant = await _get_tenant(db, tenant_id)
        if not tenant or tenant.autonomy_mode == "suggest":
            continue

        try:
            cycle_result = await run_autonomous_cycle(
                tenant_id=tenant_id,
                account_id=str(integration.id),
                db=db,
                trigger="scheduled",
            )
            results.append({
                "tenant_id": tenant_id,
                "account_id": str(integration.id),
                "result": cycle_result,
            })
        except Exception as ex:
            logger.error("Failed to run cycle for account",
                         tenant_id=tenant_id, error=str(ex))
            results.append({
                "tenant_id": tenant_id,
                "account_id": str(integration.id),
                "result": {"status": "failed", "error": str(ex)},
            })

    logger.info("Autonomous optimizer sweep completed",
                 accounts_processed=len(results))
    return {"accounts_processed": len(results), "results": results}
