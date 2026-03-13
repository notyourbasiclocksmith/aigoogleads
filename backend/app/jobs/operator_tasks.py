"""
Celery tasks for the AI Campaign Operator pipeline.
"""
import asyncio
import structlog
from app.jobs.celery_app import celery_app
from app.core.database import async_session_factory

logger = structlog.get_logger()


@celery_app.task(name="app.jobs.operator_tasks.run_operator_scan_task", bind=True, max_retries=1)
def run_operator_scan_task(self, scan_id: str):
    """
    Async Celery task that runs the full operator scan pipeline.
    """
    logger.info("Starting operator scan task", scan_id=scan_id)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_scan(scan_id))
        loop.close()
        logger.info("Operator scan task completed", scan_id=scan_id)
    except Exception as ex:
        logger.error("Operator scan task failed", scan_id=scan_id, error=str(ex))
        # Mark scan as failed
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_mark_failed(scan_id, str(ex)))
        loop.close()
        raise


@celery_app.task(name="app.jobs.operator_tasks.apply_change_set_task", bind=True, max_retries=1)
def apply_change_set_task(self, change_set_id: str):
    """
    Apply approved changes to Google Ads.
    """
    logger.info("Starting change set apply task", change_set_id=change_set_id)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_apply_changes(change_set_id))
        loop.close()
        logger.info("Change set apply task completed", change_set_id=change_set_id)
    except Exception as ex:
        logger.error("Change set apply task failed", change_set_id=change_set_id, error=str(ex))
        raise


async def _run_scan(scan_id: str):
    from app.services.operator.operator_orchestrator import run_operator_scan
    async with async_session_factory() as db:
        await run_operator_scan(scan_id, db)


async def _mark_failed(scan_id: str, error: str):
    from app.models.v2.operator_scan import OperatorScan
    async with async_session_factory() as db:
        scan = await db.get(OperatorScan, scan_id)
        if scan:
            scan.status = "failed"
            scan.error_message = error
            await db.commit()


@celery_app.task(name="app.jobs.operator_tasks.run_autonomous_optimizer_task", bind=True, max_retries=1)
def run_autonomous_optimizer_task(self):
    """
    Periodic task: run autonomous optimization for all eligible accounts.
    Scheduled every 4 hours via Celery Beat.
    """
    logger.info("Starting autonomous optimizer sweep")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run_all_autonomous())
        loop.close()
        logger.info("Autonomous optimizer sweep completed", result=result)
    except Exception as ex:
        logger.error("Autonomous optimizer sweep failed", error=str(ex))
        raise


@celery_app.task(name="app.jobs.operator_tasks.run_autonomous_cycle_task", bind=True, max_retries=1)
def run_autonomous_cycle_task(self, tenant_id: str, account_id: str, trigger: str = "manual"):
    """
    Run autonomous optimization for a single account.
    Can be triggered manually or by the periodic sweep.
    """
    logger.info("Starting autonomous cycle", tenant_id=tenant_id, account_id=account_id)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run_single_cycle(tenant_id, account_id, trigger))
        loop.close()
        logger.info("Autonomous cycle completed", result=result)
    except Exception as ex:
        logger.error("Autonomous cycle failed", tenant_id=tenant_id, error=str(ex))
        raise


@celery_app.task(name="app.jobs.operator_tasks.evaluate_cycle_feedback_task", bind=True, max_retries=2)
def evaluate_cycle_feedback_task(self, cycle_id: str):
    """
    Evaluate the results of an optimization cycle 24h after execution.
    Compares before/after metrics and triggers rollback if degraded.
    """
    logger.info("Evaluating cycle feedback", cycle_id=cycle_id)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_evaluate_feedback(cycle_id))
        loop.close()
        logger.info("Cycle feedback evaluated", cycle_id=cycle_id, result=result)
    except Exception as ex:
        logger.error("Cycle feedback evaluation failed", cycle_id=cycle_id, error=str(ex))
        raise


@celery_app.task(name="app.jobs.operator_tasks.rollback_cycle_task", bind=True, max_retries=1)
def rollback_cycle_task(self, cycle_id: str):
    """Rollback all mutations from an optimization cycle."""
    logger.info("Rolling back cycle", cycle_id=cycle_id)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_rollback_cycle(cycle_id))
        loop.close()
        logger.info("Cycle rollback completed", cycle_id=cycle_id, result=result)
    except Exception as ex:
        logger.error("Cycle rollback failed", cycle_id=cycle_id, error=str(ex))
        raise


# ── Async helpers ─────────────────────────────────────────────────────────

async def _run_all_autonomous():
    from app.services.operator.autonomous_optimizer import run_all_accounts
    async with async_session_factory() as db:
        return await run_all_accounts(db)


async def _run_single_cycle(tenant_id: str, account_id: str, trigger: str):
    from app.services.operator.autonomous_optimizer import run_autonomous_cycle
    async with async_session_factory() as db:
        return await run_autonomous_cycle(tenant_id, account_id, db, trigger)


async def _evaluate_feedback(cycle_id: str):
    from app.services.operator.feedback_loop import evaluate_cycle
    async with async_session_factory() as db:
        return await evaluate_cycle(cycle_id, db)


async def _rollback_cycle(cycle_id: str):
    from app.services.operator.feedback_loop import rollback_cycle
    async with async_session_factory() as db:
        return await rollback_cycle(cycle_id, db)


async def _apply_changes(change_set_id: str):
    """
    Execute mutations for a change set via the ExecutionEngine.
    Converts OperatorRecommendations into real Google Ads API calls.
    """
    from app.services.operator.execution_engine import ExecutionEngine
    async with async_session_factory() as db:
        engine = ExecutionEngine(db)
        result = await engine.execute_change_set(change_set_id)
        logger.info("Change set execution result",
                     change_set_id=change_set_id, result=result)
