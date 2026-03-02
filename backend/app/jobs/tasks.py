"""
Background Jobs — All Celery tasks for Ignite Ads AI.
"""
from app.jobs.celery_app import celery_app
from sqlalchemy import select, create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import settings
import structlog

logger = structlog.get_logger()

sync_engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)


def get_sync_db():
    return SyncSession()


# ── INDIVIDUAL TENANT TASKS ─────────────────────────────────────────

@celery_app.task(name="app.jobs.tasks.scan_business_task")
def scan_business_task(tenant_id: str):
    import asyncio
    asyncio.run(_scan_business_async(tenant_id))


async def _scan_business_async(tenant_id: str):
    from app.core.database import async_session_factory
    from app.models.business_profile import BusinessProfile
    from app.models.social_profile import SocialProfile
    from app.models.crawled_page import CrawledPage
    from app.services.business_scanner import BusinessScanner

    async with async_session_factory() as db:
        result = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id))
        profile = result.scalar_one_or_none()
        if not profile or not profile.website_url:
            logger.warning("No website URL for tenant", tenant_id=tenant_id)
            return

        scanner = BusinessScanner()
        try:
            scan_result = await scanner.scan_website(profile.website_url)

            profile.services_json = {"list": scan_result.get("services", [])}
            profile.locations_json = {"cities": scan_result.get("locations", [])}
            profile.offers_json = {"list": scan_result.get("offers", [])}
            profile.trust_signals_json = {"list": scan_result.get("trust_signals", [])}
            profile.brand_voice_json = {"tone": scan_result.get("brand_tone", "professional")}
            profile.snippets_json = {"list": scan_result.get("snippets", [])}
            if scan_result.get("phone_numbers"):
                profile.phone = profile.phone or scan_result["phone_numbers"][0]
            if scan_result.get("description"):
                profile.description = profile.description or scan_result["description"]

            for page in scan_result.get("pages", []):
                cp = CrawledPage(
                    tenant_id=tenant_id,
                    url=page["url"],
                    title=page.get("title", ""),
                    text_content=page.get("text_content", "")[:10000],
                    extracted_entities_json={
                        "services": page.get("extracted_services", []),
                        "locations": page.get("extracted_locations", []),
                    },
                )
                db.add(cp)

            socials = await db.execute(select(SocialProfile).where(SocialProfile.tenant_id == tenant_id))
            for sp in socials.scalars().all():
                social_data = await scanner.scan_social(sp.platform, sp.url)
                sp.extracted_bio = social_data.get("bio", "")

            await db.commit()
            logger.info("Business scan complete", tenant_id=tenant_id)
        except Exception as e:
            await db.rollback()
            logger.error("Business scan failed", tenant_id=tenant_id, error=str(e))
        finally:
            await scanner.close()


@celery_app.task(name="app.jobs.tasks.sync_ads_account_task")
def sync_ads_account_task(tenant_id: str, integration_id: str):
    import asyncio
    asyncio.run(_sync_ads_account_async(tenant_id, integration_id))


async def _sync_ads_account_async(tenant_id: str, integration_id: str):
    from app.core.database import async_session_factory
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.campaign import Campaign
    from app.models.conversion import Conversion
    from app.models.performance_daily import PerformanceDaily
    from app.integrations.google_ads.client import GoogleAdsClient
    from datetime import datetime, timezone

    async with async_session_factory() as db:
        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.id == integration_id)
        )
        integration = result.scalar_one_or_none()
        if not integration:
            return

        try:
            client = GoogleAdsClient(
                customer_id=integration.customer_id,
                refresh_token_encrypted=integration.refresh_token_encrypted,
                login_customer_id=integration.login_customer_id,
            )

            account_info = await client.get_account_info()
            if account_info.get("name"):
                integration.account_name = account_info["name"]

            campaigns = await client.get_campaigns()
            for c in campaigns:
                existing = await db.execute(
                    select(Campaign).where(
                        Campaign.tenant_id == tenant_id,
                        Campaign.campaign_id == c["campaign_id"],
                    )
                )
                camp = existing.scalar_one_or_none()
                if not camp:
                    camp = Campaign(
                        tenant_id=tenant_id,
                        google_customer_id=integration.customer_id,
                        campaign_id=c["campaign_id"],
                        type=c.get("type", "SEARCH"),
                        name=c["name"],
                        status=c["status"],
                        budget_micros=c.get("budget_micros", 0),
                        bidding_strategy=c.get("bidding_strategy"),
                        is_draft=False,
                    )
                    db.add(camp)
                else:
                    camp.name = c["name"]
                    camp.status = c["status"]
                    camp.budget_micros = c.get("budget_micros", 0)

            conv_actions = await client.get_conversion_actions()
            for ca in conv_actions:
                existing = await db.execute(
                    select(Conversion).where(
                        Conversion.tenant_id == tenant_id,
                        Conversion.action_id == ca["action_id"],
                    )
                )
                conv = existing.scalar_one_or_none()
                if not conv:
                    conv = Conversion(
                        tenant_id=tenant_id,
                        google_customer_id=integration.customer_id,
                        action_id=ca["action_id"],
                        name=ca["name"],
                        type=ca.get("type"),
                        status=ca.get("status", "ENABLED"),
                        is_primary=ca.get("category") in ("PURCHASE", "LEAD", "PHONE_CALL"),
                        last_verified_at=datetime.now(timezone.utc),
                    )
                    db.add(conv)

            metrics = await client.get_performance_metrics("LAST_30_DAYS")
            for m in metrics:
                perf = PerformanceDaily(
                    tenant_id=tenant_id,
                    entity_type="campaign",
                    entity_id=m["campaign_id"],
                    date=m["date"],
                    impressions=m.get("impressions", 0),
                    clicks=m.get("clicks", 0),
                    cost_micros=m.get("cost_micros", 0),
                    conversions=m.get("conversions", 0),
                    conv_value=m.get("conv_value", 0),
                    ctr=m.get("ctr", 0),
                    cpc_micros=m.get("avg_cpc", 0),
                )
                db.add(perf)

            integration.last_sync_at = datetime.now(timezone.utc)
            integration.health_score = 85

            await db.commit()
            logger.info("Ads account sync complete", tenant_id=tenant_id, integration_id=integration_id)
        except Exception as e:
            await db.rollback()
            logger.error("Ads account sync failed", tenant_id=tenant_id, error=str(e))


@celery_app.task(name="app.jobs.tasks.launch_campaign_task")
def launch_campaign_task(tenant_id: str, campaign_id: str, actor_id: str):
    import asyncio
    asyncio.run(_launch_campaign_async(tenant_id, campaign_id, actor_id))


async def _launch_campaign_async(tenant_id: str, campaign_id: str, actor_id: str):
    from app.core.database import async_session_factory
    from app.models.campaign import Campaign
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.change_log import ChangeLog
    from app.integrations.google_ads.client import GoogleAdsClient
    import uuid

    async with async_session_factory() as db:
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return

        integration_result = await db.execute(
            select(IntegrationGoogleAds).where(
                IntegrationGoogleAds.tenant_id == tenant_id,
                IntegrationGoogleAds.customer_id == campaign.google_customer_id,
                IntegrationGoogleAds.is_active == True,
            )
        )
        integration = integration_result.scalar_one_or_none()
        if not integration:
            campaign.status = "FAILED"
            await db.commit()
            return

        try:
            client = GoogleAdsClient(
                customer_id=integration.customer_id,
                refresh_token_encrypted=integration.refresh_token_encrypted,
                login_customer_id=integration.login_customer_id,
            )

            result = await client.create_campaign({
                "name": campaign.name,
                "budget_micros": campaign.budget_micros,
                "type": campaign.type,
                "bidding_strategy": campaign.bidding_strategy,
            })

            if result.get("status") == "created":
                campaign.status = "ENABLED"
                campaign.is_draft = False

                log = ChangeLog(
                    tenant_id=tenant_id,
                    actor_type="user",
                    actor_id=actor_id,
                    google_customer_id=campaign.google_customer_id,
                    entity_type="campaign",
                    entity_id=campaign_id,
                    before_json={"status": "DRAFT"},
                    after_json={"status": "ENABLED"},
                    reason="Campaign launched via approval flow",
                    rollback_token=str(uuid.uuid4()),
                )
                db.add(log)
            else:
                campaign.status = "FAILED"

            await db.commit()
            logger.info("Campaign launch complete", campaign_id=campaign_id, status=campaign.status)
        except Exception as e:
            campaign.status = "FAILED"
            await db.commit()
            logger.error("Campaign launch failed", campaign_id=campaign_id, error=str(e))


@celery_app.task(name="app.jobs.tasks.apply_recommendation_task")
def apply_recommendation_task(tenant_id: str, recommendation_id: str, actor_id: str):
    import asyncio
    asyncio.run(_apply_recommendation_async(tenant_id, recommendation_id, actor_id))


async def _apply_recommendation_async(tenant_id: str, recommendation_id: str, actor_id: str):
    from app.core.database import async_session_factory
    from app.services.optimization_engine import OptimizationEngine

    async with async_session_factory() as db:
        engine = OptimizationEngine(db, tenant_id)
        result = await engine.apply_recommendation(recommendation_id, actor_id)
        await db.commit()
        logger.info("Recommendation applied", rec_id=recommendation_id, result=result)


@celery_app.task(name="app.jobs.tasks.rollback_change_task")
def rollback_change_task(tenant_id: str, change_log_id: str, actor_id: str):
    import asyncio
    asyncio.run(_rollback_async(tenant_id, change_log_id, actor_id))


async def _rollback_async(tenant_id: str, change_log_id: str, actor_id: str):
    from app.core.database import async_session_factory
    from app.services.optimization_engine import OptimizationEngine

    async with async_session_factory() as db:
        engine = OptimizationEngine(db, tenant_id)
        result = await engine.rollback_change(change_log_id, actor_id)
        await db.commit()
        logger.info("Rollback complete", change_log_id=change_log_id, result=result)


@celery_app.task(name="app.jobs.tasks.run_serp_scan_task")
def run_serp_scan_task(tenant_id: str, keywords: list, geo: str = None, device: str = "desktop"):
    logger.info("SERP scan task started", tenant_id=tenant_id, keywords=len(keywords))


@celery_app.task(name="app.jobs.tasks.generate_report_task")
def generate_report_task(tenant_id: str, report_type: str, period_days: int):
    import asyncio
    asyncio.run(_generate_report_async(tenant_id, report_type, period_days))


async def _generate_report_async(tenant_id: str, report_type: str, period_days: int):
    from app.core.database import async_session_factory
    from app.services.report_service import ReportService

    async with async_session_factory() as db:
        svc = ReportService(db, tenant_id)
        report = await svc.generate_weekly_report(period_days)
        logger.info("Report generated", tenant_id=tenant_id, type=report_type)


@celery_app.task(name="app.jobs.tasks.start_experiment_task")
def start_experiment_task(tenant_id: str, experiment_id: str):
    logger.info("Experiment started", tenant_id=tenant_id, experiment_id=experiment_id)


@celery_app.task(name="app.jobs.tasks.promote_experiment_winner_task")
def promote_experiment_winner_task(tenant_id: str, experiment_id: str, variant_index: int):
    logger.info("Promoting experiment winner", tenant_id=tenant_id, experiment_id=experiment_id, variant=variant_index)


# ── SCHEDULED GLOBAL TASKS ──────────────────────────────────────────

@celery_app.task(name="app.jobs.tasks.sync_all_ads_hourly")
def sync_all_ads_hourly():
    import asyncio
    asyncio.run(_sync_all_hourly())


async def _sync_all_hourly():
    from app.core.database import async_session_factory
    from app.models.integration_google_ads import IntegrationGoogleAds

    async with async_session_factory() as db:
        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.is_active == True)
        )
        integrations = result.scalars().all()
        for integration in integrations:
            sync_ads_account_task.delay(integration.tenant_id, integration.id)
        logger.info("Hourly sync dispatched", count=len(integrations))


@celery_app.task(name="app.jobs.tasks.sync_all_ads_daily")
def sync_all_ads_daily():
    sync_all_ads_hourly()


@celery_app.task(name="app.jobs.tasks.run_all_diagnostics")
def run_all_diagnostics():
    import asyncio
    asyncio.run(_run_all_diagnostics())


async def _run_all_diagnostics():
    from app.core.database import async_session_factory
    from app.models.tenant import Tenant
    from app.services.diagnostic_engine import DiagnosticEngine

    async with async_session_factory() as db:
        result = await db.execute(select(Tenant))
        tenants = result.scalars().all()
        for tenant in tenants:
            try:
                engine = DiagnosticEngine(db, tenant.id)
                await engine.run_full_diagnostic()
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error("Diagnostic failed for tenant", tenant_id=tenant.id, error=str(e))
        logger.info("All diagnostics complete", count=len(tenants))


@celery_app.task(name="app.jobs.tasks.generate_all_recommendations")
def generate_all_recommendations():
    run_all_diagnostics()


@celery_app.task(name="app.jobs.tasks.apply_all_autopilot")
def apply_all_autopilot():
    import asyncio
    asyncio.run(_apply_all_autopilot())


async def _apply_all_autopilot():
    from app.core.database import async_session_factory
    from app.models.tenant import Tenant
    from app.services.optimization_engine import OptimizationEngine

    async with async_session_factory() as db:
        result = await db.execute(
            select(Tenant).where(Tenant.autonomy_mode.in_(["semi_auto", "full_auto"]))
        )
        tenants = result.scalars().all()
        for tenant in tenants:
            try:
                engine = OptimizationEngine(db, tenant.id)
                applied = await engine.apply_auto_recommendations()
                await db.commit()
                if applied:
                    logger.info("Autopilot applied changes", tenant_id=tenant.id, count=len(applied))
            except Exception as e:
                await db.rollback()
                logger.error("Autopilot failed for tenant", tenant_id=tenant.id, error=str(e))


@celery_app.task(name="app.jobs.tasks.run_all_serp_scans")
def run_all_serp_scans():
    logger.info("Weekly SERP scan task started")


@celery_app.task(name="app.jobs.tasks.crawl_all_websites")
def crawl_all_websites():
    import asyncio
    asyncio.run(_crawl_all_websites())


async def _crawl_all_websites():
    from app.core.database import async_session_factory
    from app.models.business_profile import BusinessProfile

    async with async_session_factory() as db:
        result = await db.execute(
            select(BusinessProfile).where(BusinessProfile.website_url.isnot(None))
        )
        profiles = result.scalars().all()
        for profile in profiles:
            scan_business_task.delay(profile.tenant_id)
        logger.info("Website crawl dispatched", count=len(profiles))


@celery_app.task(name="app.jobs.tasks.generate_all_weekly_reports")
def generate_all_weekly_reports():
    import asyncio
    asyncio.run(_generate_all_reports("weekly", 7))


@celery_app.task(name="app.jobs.tasks.generate_all_monthly_reports")
def generate_all_monthly_reports():
    import asyncio
    asyncio.run(_generate_all_reports("monthly", 30))


async def _generate_all_reports(report_type: str, period_days: int):
    from app.core.database import async_session_factory
    from app.models.tenant import Tenant

    async with async_session_factory() as db:
        result = await db.execute(select(Tenant))
        tenants = result.scalars().all()
        for tenant in tenants:
            generate_report_task.delay(tenant.id, report_type, period_days)
        logger.info(f"{report_type} reports dispatched", count=len(tenants))


@celery_app.task(name="app.jobs.tasks.aggregate_learnings")
def aggregate_learnings():
    logger.info("Learning aggregation task started")
