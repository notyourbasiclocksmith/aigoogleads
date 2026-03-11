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


async def _apply_changes(change_set_id: str):
    """
    Execute mutations for a change set.
    This will be expanded when Google Ads mutation adapters are built.
    For now, marks the change set as applied with a placeholder.
    """
    from app.models.v2.operator_change_set import OperatorChangeSet
    from datetime import datetime, timezone
    async with async_session_factory() as db:
        cs = await db.get(OperatorChangeSet, change_set_id)
        if not cs:
            return
        cs.status = "applying"
        await db.commit()

        # TODO: Execute actual Google Ads mutations here via mutation_executor
        # For now, mark as applied (mutations will be built in Phase 9)
        cs.status = "applied"
        cs.applied_at = datetime.now(timezone.utc)
        cs.apply_summary_json = {"note": "Mutation execution pending Basic Access approval"}
        await db.commit()
