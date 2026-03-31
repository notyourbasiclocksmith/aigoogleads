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
    from app.models.performance_daily import PerformanceDaily
    from app.services.v2.change_management import evaluate_rollback_triggers
    from app.services.v2.notification_service import dispatch_notification
    from sqlalchemy import select, and_, func
    from datetime import date, timedelta

    async with async_session_factory() as db:
        try:
            stmt = select(RollbackPolicy).where(RollbackPolicy.enabled == True)
            result = await db.execute(stmt)
            policies = result.scalars().all()

            today = date.today()
            current_start = today - timedelta(days=7)
            baseline_start = today - timedelta(days=14)
            baseline_end = today - timedelta(days=8)

            for policy in policies:
                # Query actual current metrics (last 7 days)
                current_q = await db.execute(
                    select(
                        func.sum(PerformanceDaily.conversions).label("conversions"),
                        func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                        func.sum(PerformanceDaily.cpa_micros).label("cpa_micros_sum"),
                        func.count().label("rows"),
                    ).where(
                        and_(
                            PerformanceDaily.tenant_id == policy.tenant_id,
                            PerformanceDaily.date >= current_start,
                            PerformanceDaily.date <= today,
                        )
                    )
                )
                cur = current_q.one()

                # Query baseline metrics (prior 7 days)
                base_q = await db.execute(
                    select(
                        func.sum(PerformanceDaily.conversions).label("conversions"),
                        func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                        func.sum(PerformanceDaily.cpa_micros).label("cpa_micros_sum"),
                        func.count().label("rows"),
                    ).where(
                        and_(
                            PerformanceDaily.tenant_id == policy.tenant_id,
                            PerformanceDaily.date >= baseline_start,
                            PerformanceDaily.date <= baseline_end,
                        )
                    )
                )
                base = base_q.one()

                if not cur.rows or not base.rows:
                    # No performance data yet — skip evaluation
                    continue

                MICROS = 1_000_000
                current_metrics = {
                    "conversions": float(cur.conversions or 0),
                    "cpa": (cur.cpa_micros_sum or 0) / MICROS / max(cur.rows, 1),
                    "spend": (cur.cost_micros or 0) / MICROS,
                }
                baseline_metrics = {
                    "conversions": float(base.conversions or 0),
                    "cpa": (base.cpa_micros_sum or 0) / MICROS / max(base.rows, 1),
                    "spend": (base.cost_micros or 0) / MICROS,
                }

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
    from app.models.performance_daily import PerformanceDaily
    from app.services.v2.evaluation import record_outcome
    from sqlalchemy import select, and_, func
    from datetime import datetime, timezone, timedelta, date as date_type

    async with async_session_factory() as db:
        try:
            now = datetime.now(timezone.utc)
            MICROS = 1_000_000

            for window_days in [7, 14, 30]:
                target_date = now - timedelta(days=window_days)
                window_start = target_date - timedelta(hours=12)
                window_end = target_date + timedelta(hours=12)

                stmt = select(Recommendation).where(
                    and_(
                        Recommendation.status == "applied",
                        Recommendation.applied_at >= window_start,
                        Recommendation.applied_at <= window_end,
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

                    # Compute actual before/after performance delta for this tenant
                    applied_date = rec.applied_at.date() if rec.applied_at else None
                    if not applied_date:
                        continue

                    before_start = applied_date - timedelta(days=window_days)
                    before_end = applied_date - timedelta(days=1)
                    after_start = applied_date
                    after_end = applied_date + timedelta(days=window_days - 1)

                    async def _agg(start, end):
                        q = await db.execute(
                            select(
                                func.sum(PerformanceDaily.conversions).label("conversions"),
                                func.sum(PerformanceDaily.cost_micros).label("cost_micros"),
                                func.sum(PerformanceDaily.conv_value).label("conv_value"),
                            ).where(
                                and_(
                                    PerformanceDaily.tenant_id == rec.tenant_id,
                                    PerformanceDaily.date >= start,
                                    PerformanceDaily.date <= end,
                                )
                            )
                        )
                        return q.one()

                    before = await _agg(before_start, before_end)
                    after = await _agg(after_start, after_end)

                    before_conversions = float(before.conversions or 0)
                    after_conversions = float(after.conversions or 0)
                    before_spend = (before.cost_micros or 0) / MICROS
                    after_spend = (after.cost_micros or 0) / MICROS
                    before_cpa = before_spend / before_conversions if before_conversions else 0
                    after_cpa = after_spend / after_conversions if after_conversions else 0
                    before_roas = (float(before.conv_value or 0)) / before_spend if before_spend else 0
                    after_roas = (float(after.conv_value or 0)) / after_spend if after_spend else 0

                    actual_metrics = {
                        "conversions_delta": round(after_conversions - before_conversions, 2),
                        "cpa_delta": round(after_cpa - before_cpa, 4),
                        "roas_delta": round(after_roas - before_roas, 4),
                        "spend_before": round(before_spend, 2),
                        "spend_after": round(after_spend, 2),
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
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.v2.google_ads_accessible_account import GoogleAdsAccessibleAccount
    from app.core.config import settings
    from sqlalchemy import select, and_
    from datetime import datetime, timezone
    import httpx

    logger.info("MCC account sync started", tenant_id=tenant_id)

    async with async_session_factory() as db:
        try:
            int_stmt = select(IntegrationGoogleAds).where(
                and_(
                    IntegrationGoogleAds.tenant_id == tenant_id,
                    IntegrationGoogleAds.is_active == True,
                )
            )
            int_result = await db.execute(int_stmt)
            integration = int_result.scalars().first()

            if not integration:
                logger.warning("No active Google Ads integration for MCC sync", tenant_id=tenant_id)
                return

            manager_id = (integration.login_customer_id or integration.customer_id).replace("-", "")
            headers = {
                "Authorization": f"Bearer {integration.access_token_cache}",
                "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                "login-customer-id": manager_id,
                "Content-Type": "application/json",
            }

            # Use the Google Ads Query Language to list accessible customers
            query = (
                "SELECT customer_client.client_customer, customer_client.descriptive_name, "
                "customer_client.currency_code, customer_client.time_zone, "
                "customer_client.status "
                "FROM customer_client "
                "WHERE customer_client.level <= 1"
            )
            api_url = f"https://googleads.googleapis.com/v17/customers/{manager_id}/googleAds:search"

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(api_url, json={"query": query}, headers=headers)

            if resp.status_code != 200:
                logger.error(
                    "Google Ads MCC API error",
                    tenant_id=tenant_id,
                    status_code=resp.status_code,
                    body=resp.text[:500],
                )
                return

            rows = resp.json().get("results", [])
            now = datetime.now(timezone.utc)

            for row in rows:
                cc = row.get("customerClient", {})
                raw_resource = cc.get("clientCustomer", "")
                # resource name format: customers/1234567890
                customer_id = raw_resource.split("/")[-1] if "/" in raw_resource else raw_resource

                if not customer_id or customer_id == manager_id:
                    continue

                # Upsert accessible account record
                existing_q = await db.execute(
                    select(GoogleAdsAccessibleAccount).where(
                        and_(
                            GoogleAdsAccessibleAccount.tenant_id == tenant_id,
                            GoogleAdsAccessibleAccount.customer_id == customer_id,
                        )
                    )
                )
                account = existing_q.scalars().first()

                if account:
                    account.descriptive_name = cc.get("descriptiveName")
                    account.currency = cc.get("currencyCode")
                    account.timezone = cc.get("timeZone")
                    account.status = cc.get("status")
                    account.last_seen_at = now
                else:
                    db.add(
                        GoogleAdsAccessibleAccount(
                            tenant_id=tenant_id,
                            manager_customer_id=manager_id,
                            customer_id=customer_id,
                            descriptive_name=cc.get("descriptiveName"),
                            currency=cc.get("currencyCode"),
                            timezone=cc.get("timeZone"),
                            status=cc.get("status"),
                            last_seen_at=now,
                        )
                    )

            await db.commit()
            logger.info("MCC account sync complete", tenant_id=tenant_id, accounts_found=len(rows))

        except Exception as e:
            await db.rollback()
            logger.error("sync_mcc_accounts failed", tenant_id=tenant_id, error=str(e))


# ── Offline Conversion Upload to Google ──
@celery_app.task(name="app.jobs.v2_tasks.push_offline_conversions")
def push_offline_conversions_task(tenant_id: str, upload_id: str):
    """Push pending offline conversions to Google Ads via API."""
    import asyncio
    asyncio.run(_push_offline_conversions_async(tenant_id, upload_id))


async def _push_offline_conversions_async(tenant_id: str, upload_id: str):
    from app.core.database import async_session_factory
    from app.models.v2.offline_conversion import OfflineConversion
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.core.config import settings
    from sqlalchemy import select, and_
    import httpx

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

            if not conversions:
                logger.info("No pending offline conversions found", tenant_id=tenant_id, upload_id=upload_id)
                return

            # Fetch the Google Ads integration for this tenant to get credentials
            int_stmt = select(IntegrationGoogleAds).where(
                and_(
                    IntegrationGoogleAds.tenant_id == tenant_id,
                    IntegrationGoogleAds.is_active == True,
                )
            )
            int_result = await db.execute(int_stmt)
            integration = int_result.scalars().first()

            if not integration:
                logger.error("No active Google Ads integration for tenant", tenant_id=tenant_id)
                for conv in conversions:
                    conv.status = "failed"
                await db.commit()
                return

            # Build the Google Ads API click conversions payload
            customer_id = conversions[0].google_customer_id.replace("-", "")
            click_conversions = [
                {
                    "gclid": conv.gclid,
                    "conversionAction": f"customers/{customer_id}/conversionActions/{conv.conversion_name}",
                    "conversionDateTime": conv.conversion_time.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "conversionValue": float(conv.value or 0),
                    "currencyCode": conv.currency or "USD",
                }
                for conv in conversions
            ]

            payload = {
                "conversions": click_conversions,
                "partialFailure": True,
            }

            api_url = (
                f"https://googleads.googleapis.com/v17/customers/{customer_id}"
                f"/conversionUploads:uploadClickConversions"
            )
            headers = {
                "Authorization": f"Bearer {integration.access_token_cache}",
                "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
                "Content-Type": "application/json",
            }
            if integration.login_customer_id:
                headers["login-customer-id"] = integration.login_customer_id

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(api_url, json=payload, headers=headers)

            if resp.status_code == 200:
                resp_data = resp.json()
                partial_errors = resp_data.get("partialFailureError")
                if partial_errors:
                    logger.warning(
                        "Offline conversion upload partial failure",
                        tenant_id=tenant_id,
                        errors=partial_errors,
                    )
                for conv in conversions:
                    conv.status = "uploaded"
                logger.info(
                    "Offline conversions uploaded to Google Ads",
                    tenant_id=tenant_id,
                    count=len(conversions),
                )
            else:
                logger.error(
                    "Google Ads conversion upload API error",
                    tenant_id=tenant_id,
                    status_code=resp.status_code,
                    body=resp.text[:500],
                )
                for conv in conversions:
                    conv.status = "failed"

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("push_offline_conversions failed", error=str(e))
