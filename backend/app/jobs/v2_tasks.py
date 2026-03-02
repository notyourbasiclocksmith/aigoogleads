"""
V2 Background Jobs — Celery tasks for change scheduling, rollback evaluation,
recommendation outcome recording, and notification dispatch.
"""
from app.jobs.celery_app import celery_app
from app.core.config import settings
import structlog

logger = structlog.get_logger()


# ── Scheduled Change Sets ──
@celery_app.task(name="app.jobs.v2_tasks.apply_due_change_sets")
def apply_due_change_sets():
    """Periodic: find and apply all change sets past their scheduled time."""
    import asyncio
    asyncio.run(_apply_due_change_sets_async())


async def _apply_due_change_sets_async():
    from app.core.database import async_session_factory
    from app.services.v2.change_management import get_due_scheduled_sets, apply_change_set

    async with async_session_factory() as db:
        try:
            due_sets = await get_due_scheduled_sets(db)
            for cs in due_sets:
                logger.info("Applying scheduled change set", change_set_id=cs.id, tenant_id=cs.tenant_id)
                result = await apply_change_set(db, cs.tenant_id, cs.id)
                if not result.get("applied"):
                    logger.warning("Failed to apply change set", change_set_id=cs.id, error=result.get("error"))
            await db.commit()
            logger.info("Scheduled change sets processed", count=len(due_sets))
        except Exception as e:
            await db.rollback()
            logger.error("apply_due_change_sets failed", error=str(e))


# ── Rollback Trigger Evaluation ──
@celery_app.task(name="app.jobs.v2_tasks.evaluate_rollback_triggers")
def evaluate_rollback_triggers_task():
    """Periodic: check all tenants for rollback trigger violations."""
    import asyncio
    asyncio.run(_evaluate_rollback_triggers_async())


async def _evaluate_rollback_triggers_async():
    from app.core.database import async_session_factory
    from app.models.tenant import Tenant
    from app.models.v2.rollback_policy import RollbackPolicy
    from app.services.v2.change_management import evaluate_rollback_triggers
    from app.services.v2.notification_service import dispatch_notification
    from sqlalchemy import select, and_

    async with async_session_factory() as db:
        try:
            stmt = select(RollbackPolicy).where(RollbackPolicy.enabled == True)
            result = await db.execute(stmt)
            policies = result.scalars().all()

            for policy in policies:
                # Stub: in production, fetch actual current vs baseline metrics
                current_metrics = {"conversions": 10, "cpa": 45, "spend": 500}
                baseline_metrics = {"conversions": 12, "cpa": 40, "spend": 450}

                eval_result = await evaluate_rollback_triggers(
                    db, policy.tenant_id, current_metrics, baseline_metrics
                )

                if eval_result["triggered"]:
                    logger.warning(
                        "Rollback trigger fired",
                        tenant_id=policy.tenant_id,
                        violations=eval_result["violations"],
                    )
                    await dispatch_notification(
                        db, policy.tenant_id,
                        event_type="rollback_trigger",
                        severity="critical",
                        payload={
                            "message": f"Rollback trigger fired: {len(eval_result['violations'])} violations detected",
                            "violations": eval_result["violations"],
                        },
                    )
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("evaluate_rollback_triggers failed", error=str(e))


# ── Recommendation Outcome Recording ──
@celery_app.task(name="app.jobs.v2_tasks.record_recommendation_outcomes")
def record_recommendation_outcomes_task():
    """Periodic: record outcomes for recommendations applied 7, 14, 30 days ago."""
    import asyncio
    asyncio.run(_record_recommendation_outcomes_async())


async def _record_recommendation_outcomes_async():
    from app.core.database import async_session_factory
    from app.models.recommendation import Recommendation
    from app.models.v2.recommendation_outcome import RecommendationOutcome
    from app.services.v2.evaluation import record_outcome
    from sqlalchemy import select, and_
    from datetime import datetime, timezone, timedelta

    async with async_session_factory() as db:
        try:
            now = datetime.now(timezone.utc)
            for window_days in [7, 14, 30]:
                target_date = now - timedelta(days=window_days)
                window_start = target_date - timedelta(hours=12)
                window_end = target_date + timedelta(hours=12)

                stmt = select(Recommendation).where(
                    and_(
                        Recommendation.status == "applied",
                        Recommendation.updated_at >= window_start,
                        Recommendation.updated_at <= window_end,
                    )
                )
                result = await db.execute(stmt)
                recs = result.scalars().all()

                for rec in recs:
                    # Check if outcome already recorded
                    existing = await db.execute(
                        select(RecommendationOutcome).where(
                            and_(
                                RecommendationOutcome.recommendation_id == rec.id,
                                RecommendationOutcome.window_days == window_days,
                            )
                        )
                    )
                    if existing.scalars().first():
                        continue

                    # Stub: in production, compute actual metrics delta
                    actual_metrics = {
                        "conversions_delta": 2,
                        "cpa_delta": -3,
                        "roas_delta": 0.15,
                    }
                    await record_outcome(db, rec.id, window_days, actual_metrics)

            await db.commit()
            logger.info("Recommendation outcomes recorded")
        except Exception as e:
            await db.rollback()
            logger.error("record_recommendation_outcomes failed", error=str(e))


# ── Regression Check ──
@celery_app.task(name="app.jobs.v2_tasks.check_evaluation_regression")
def check_evaluation_regression_task():
    """Periodic: check for prediction accuracy regression."""
    import asyncio
    asyncio.run(_check_evaluation_regression_async())


async def _check_evaluation_regression_async():
    from app.core.database import async_session_factory
    from app.services.v2.evaluation import check_regression
    from app.services.v2.notification_service import dispatch_notification

    async with async_session_factory() as db:
        try:
            result = await check_regression(db, threshold_error_pct=30.0)
            if result["regression_detected"]:
                logger.warning("Evaluation regression detected", details=result["details"])
                # Notify admins — uses global tenant_id placeholder
                # In production, notify all admin users
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("check_evaluation_regression failed", error=str(e))


# ── MCC Account Discovery Sync ──
@celery_app.task(name="app.jobs.v2_tasks.sync_mcc_accounts")
def sync_mcc_accounts_task(tenant_id: str):
    """Trigger MCC account discovery for a specific tenant."""
    import asyncio
    asyncio.run(_sync_mcc_accounts_async(tenant_id))


async def _sync_mcc_accounts_async(tenant_id: str):
    from app.core.database import async_session_factory
    logger.info("MCC account sync triggered (stub)", tenant_id=tenant_id)
    # In production: call Google Ads API to list accessible customers


# ── Offline Conversion Upload to Google ──
@celery_app.task(name="app.jobs.v2_tasks.push_offline_conversions")
def push_offline_conversions_task(tenant_id: str, upload_id: str):
    """Push pending offline conversions to Google Ads via API."""
    import asyncio
    asyncio.run(_push_offline_conversions_async(tenant_id, upload_id))


async def _push_offline_conversions_async(tenant_id: str, upload_id: str):
    from app.core.database import async_session_factory
    from app.models.v2.offline_conversion import OfflineConversion
    from sqlalchemy import select, and_

    async with async_session_factory() as db:
        try:
            stmt = select(OfflineConversion).where(
                and_(
                    OfflineConversion.tenant_id == tenant_id,
                    OfflineConversion.upload_id == upload_id,
                    OfflineConversion.status == "pending",
                )
            )
            result = await db.execute(stmt)
            conversions = result.scalars().all()
            # Stub: would call Google Ads ConversionUploadService
            for conv in conversions:
                conv.status = "uploaded"
            await db.commit()
            logger.info("Offline conversions pushed (stub)", tenant_id=tenant_id, count=len(conversions))
        except Exception as e:
            await db.rollback()
            logger.error("push_offline_conversions failed", error=str(e))
