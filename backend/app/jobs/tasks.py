"""
Background Jobs — All Celery tasks for Ignite Ads AI.
"""
from app.jobs.celery_app import celery_app
from sqlalchemy import select, and_, func, delete, create_engine
from tenacity import RetryError
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


@celery_app.task(name="app.jobs.tasks.analyze_business_task")
def analyze_business_task(tenant_id: str):
    import asyncio
    asyncio.run(_analyze_business_async(tenant_id))


async def _analyze_business_async(tenant_id: str):
    from app.core.database import async_session_factory
    from app.models.business_profile import BusinessProfile
    from app.models.social_profile import SocialProfile
    from app.models.tenant import Tenant
    from app.services.social_analyzer import SocialAnalyzer
    from datetime import datetime, timezone

    async with async_session_factory() as db:
        # Load tenant + profile + social links
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            logger.error("Tenant not found for analysis", tenant_id=tenant_id)
            return

        result2 = await db.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id))
        profile = result2.scalar_one_or_none()

        result3 = await db.execute(select(SocialProfile).where(SocialProfile.tenant_id == tenant_id))
        socials = result3.scalars().all()

        analyzer = SocialAnalyzer()
        try:
            analysis = await analyzer.analyze(
                business_name=tenant.name or "Unknown Business",
                industry=tenant.industry or profile.industry_classification if profile else "",
                phone=profile.phone if profile else "",
                website_url=profile.website_url if profile else None,
                social_profiles=[{"platform": s.platform, "url": s.url} for s in socials],
            )

            # Enrich BusinessProfile with AI insights
            if profile:
                if analysis.get("business_summary"):
                    profile.description = analysis["business_summary"]
                if analysis.get("services"):
                    profile.services_json = {"list": analysis["services"]}
                if analysis.get("service_areas"):
                    profile.locations_json = {"cities": analysis["service_areas"]}
                if analysis.get("unique_selling_points"):
                    profile.usp_json = {"list": analysis["unique_selling_points"]}
                if analysis.get("brand_voice"):
                    profile.brand_voice_json = analysis["brand_voice"]
                if analysis.get("trust_signals"):
                    profile.trust_signals_json = {"list": analysis["trust_signals"]}
                if analysis.get("offers_and_promotions"):
                    profile.offers_json = {"list": analysis["offers_and_promotions"]}
                if analysis.get("competitor_keywords"):
                    profile.competitor_targets_json = {"keywords": analysis["competitor_keywords"]}
                if analysis.get("google_ads_recommendations"):
                    profile.snippets_json = {
                        "ai_recommendations": analysis["google_ads_recommendations"],
                        "target_audience": analysis.get("target_audience", {}),
                    }
                # Store full analysis in constraints_json for reference
                profile.constraints_json = {
                    **(profile.constraints_json or {}),
                    "ai_analysis": {
                        "status": analysis.get("_ai_status", "unknown"),
                        "social_assessment": analysis.get("social_media_assessment", {}),
                        "website_assessment": analysis.get("website_assessment", {}),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
                profile.updated_at = datetime.now(timezone.utc)

            # Update social profiles with extracted data
            crawled = analysis.get("_crawled", {})
            social_crawled = crawled.get("social_data", [])
            for crawled_social in social_crawled:
                for sp in socials:
                    if sp.url == crawled_social.get("url"):
                        sp.extracted_bio = crawled_social.get("meta_description") or crawled_social.get("content", "")[:500]
                        sp.updated_at = datetime.now(timezone.utc)

            await db.commit()
            logger.info("Business analysis saved", tenant_id=tenant_id, ai_status=analysis.get("_ai_status"))
        except Exception as e:
            await db.rollback()
            logger.error("Business analysis failed", tenant_id=tenant_id, error=str(e))
        finally:
            await analyzer.close()


@celery_app.task(name="app.jobs.tasks.sync_ads_account_task")
def sync_ads_account_task(tenant_id: str, integration_id: str, full_sync: bool = True):
    import asyncio
    asyncio.run(_sync_ads_account_async(tenant_id, integration_id, full_sync=full_sync))


async def _update_sync_progress(db, integration, status: str, message: str, progress: int, **kwargs):
    """Helper to flush sync progress to DB so the frontend can poll it."""
    integration.sync_status = status
    integration.sync_message = message
    integration.sync_progress = progress
    for k, v in kwargs.items():
        if hasattr(integration, k):
            setattr(integration, k, v)
    await db.commit()


async def _sync_ads_account_async(tenant_id: str, integration_id: str, full_sync: bool = True):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.models.campaign import Campaign
    from app.models.ad_group import AdGroup
    from app.models.ad import Ad
    from app.models.keyword import Keyword
    from app.models.conversion import Conversion
    from app.models.performance_daily import PerformanceDaily
    from app.models.keyword_performance_daily import KeywordPerformanceDaily
    from app.models.ad_performance_daily import AdPerformanceDaily
    from app.models.ad_group_performance_daily import AdGroupPerformanceDaily
    from app.models.search_term_performance import SearchTermPerformance
    from app.models.landing_page_performance import LandingPagePerformance
    from app.models.auction_insight import AuctionInsight
    from app.models.google_recommendation import GoogleRecommendation
    from app.models.lsa_lead import LSALead
    from app.models.lsa_conversation import LSAConversation
    from app.integrations.google_ads.client import GoogleAdsClient
    from datetime import datetime, timezone

    # Create a fresh engine for this task — each asyncio.run() has its own event loop,
    # so we cannot reuse the global async engine whose pool is tied to a different loop.
    task_engine = create_async_engine(
        settings.DATABASE_URL, pool_size=5, max_overflow=5, pool_pre_ping=True,
    )
    task_session_factory = async_sessionmaker(
        task_engine, class_=AsyncSession, expire_on_commit=False,
    )

    async with task_session_factory() as db:
        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.id == integration_id)
        )
        integration = result.scalar_one_or_none()
        if not integration:
            await task_engine.dispose()
            return

        try:
            # Step 1: Start sync
            await _update_sync_progress(
                db, integration, "syncing", "Connecting to Google Ads...", 5,
                sync_started_at=datetime.now(timezone.utc), sync_error=None,
                campaigns_synced=0, conversions_synced=0,
            )

            client = GoogleAdsClient(
                customer_id=integration.customer_id,
                refresh_token_encrypted=integration.refresh_token_encrypted,
                login_customer_id=integration.login_customer_id,
            )

            # Auto-detect manager (MCC) account and clear login_customer_id if user has direct access
            await _update_sync_progress(db, integration, "syncing", "Detecting manager account...", 7)
            try:
                raw_client = client._get_client()
                customer_service = raw_client.get_service("CustomerService")
                accessible = customer_service.list_accessible_customers()
                ga_svc = raw_client.get_service("GoogleAdsService")
                for rn in accessible.resource_names:
                    cid = rn.split("/")[-1]
                    if cid == integration.customer_id:
                        continue
                    try:
                        q = "SELECT customer.id, customer.manager FROM customer LIMIT 1"
                        for row in ga_svc.search(customer_id=cid, query=q):
                            if row.customer.manager:
                                # Manager found, but user has direct access to target account
                                # Clear login_customer_id to avoid USER_PERMISSION_DENIED
                                integration.login_customer_id = None
                                await db.commit()
                                logger.info("Auto-detected manager account, clearing login_customer_id for direct access",
                                            manager_cid=cid,
                                            customer_id=integration.customer_id)
                                client = GoogleAdsClient(
                                    customer_id=integration.customer_id,
                                    refresh_token_encrypted=integration.refresh_token_encrypted,
                                    login_customer_id=None,
                                )
                                break
                    except Exception:
                        continue
                    if not integration.login_customer_id:
                        break
                if integration.login_customer_id:
                    logger.info("No changes needed, proceeding with current login_customer_id")
                else:
                    logger.info("Proceeding without login_customer_id (direct access)")
            except Exception as mcc_err:
                logger.warning("Could not auto-detect manager account", error=str(mcc_err))

            # Determine sync mode and date range
            sync_mode = "full" if full_sync else "light"
            date_range = "LAST_30_DAYS" if full_sync else "LAST_7_DAYS"
            logger.info("Sync mode", mode=sync_mode, date_range=date_range, tenant_id=tenant_id)

            # Step 2: Account info
            await _update_sync_progress(db, integration, "syncing", f"Fetching account info ({sync_mode} sync)...", 10)
            account_info = await client.get_account_info()
            if account_info.get("name"):
                integration.account_name = account_info["name"]

            # Step 3: Campaigns
            await _update_sync_progress(db, integration, "syncing", "Pulling campaigns...", 15)
            campaigns = await client.get_campaigns()
            campaign_count = 0
            # Build a mapping from google campaign_id -> our Campaign UUID
            google_id_to_uuid = {}
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
                    await db.flush()  # flush to get camp.id
                else:
                    camp.name = c["name"]
                    camp.status = c["status"]
                    camp.budget_micros = c.get("budget_micros", 0)
                    camp.bidding_strategy = c.get("bidding_strategy") or camp.bidding_strategy
                google_id_to_uuid[c["campaign_id"]] = camp.id
                campaign_count += 1
            await _update_sync_progress(
                db, integration, "syncing",
                f"Synced {campaign_count} campaigns",
                25, campaigns_synced=campaign_count,
            )

            # Step 4: Ad groups, keywords, and ads for each campaign
            # (skipped during lightweight hourly sync — structure rarely changes)
            total_ag = 0
            total_kw = 0
            total_ad = 0
            if not full_sync:
                await _update_sync_progress(db, integration, "syncing", "Lightweight sync — skipping structure pull", 50)
            for idx, c in enumerate(campaigns if full_sync else []):
                camp_uuid = google_id_to_uuid.get(c["campaign_id"])
                if not camp_uuid:
                    continue

                pct = 25 + int((idx / max(len(campaigns), 1)) * 25)
                await _update_sync_progress(
                    db, integration, "syncing",
                    f"Pulling ad groups for '{c['name']}'...", pct,
                )

                ad_groups = await client.get_ad_groups(c["campaign_id"])
                for ag in ad_groups:
                    existing_ag = await db.execute(
                        select(AdGroup).where(
                            AdGroup.tenant_id == tenant_id,
                            AdGroup.ad_group_id == ag["ad_group_id"],
                        )
                    )
                    ad_grp = existing_ag.scalar_one_or_none()
                    if not ad_grp:
                        ad_grp = AdGroup(
                            tenant_id=tenant_id,
                            campaign_id=camp_uuid,
                            ad_group_id=ag["ad_group_id"],
                            name=ag["name"],
                            status=ag["status"],
                        )
                        db.add(ad_grp)
                        await db.flush()
                    else:
                        ad_grp.name = ag["name"]
                        ad_grp.status = ag["status"]
                    total_ag += 1

                    # Keywords for this ad group
                    keywords = await client.get_keywords(ag["ad_group_id"])
                    for kw in keywords:
                        existing_kw = await db.execute(
                            select(Keyword).where(
                                Keyword.tenant_id == tenant_id,
                                Keyword.keyword_id == kw["keyword_id"],
                            )
                        )
                        kw_obj = existing_kw.scalar_one_or_none()
                        if not kw_obj:
                            kw_obj = Keyword(
                                tenant_id=tenant_id,
                                ad_group_id=ad_grp.id,
                                keyword_id=kw["keyword_id"],
                                text=kw["text"],
                                match_type=kw["match_type"],
                                status=kw["status"],
                                quality_score=kw.get("quality_score"),
                                cpc_bid_micros=kw.get("cpc_bid_micros", 0),
                            )
                            db.add(kw_obj)
                        else:
                            kw_obj.text = kw["text"]
                            kw_obj.match_type = kw["match_type"]
                            kw_obj.status = kw["status"]
                            kw_obj.quality_score = kw.get("quality_score")
                            kw_obj.cpc_bid_micros = kw.get("cpc_bid_micros", 0)
                        total_kw += 1

                    # Ads for this ad group
                    ads = await client.get_ads(ag["ad_group_id"])
                    for ad in ads:
                        existing_ad = await db.execute(
                            select(Ad).where(
                                Ad.tenant_id == tenant_id,
                                Ad.ad_id == ad["ad_id"],
                            )
                        )
                        ad_obj = existing_ad.scalar_one_or_none()
                        if not ad_obj:
                            ad_obj = Ad(
                                tenant_id=tenant_id,
                                ad_group_id=ad_grp.id,
                                ad_id=ad["ad_id"],
                                ad_type=ad.get("type", "RESPONSIVE_SEARCH_AD"),
                                headlines_json=ad.get("headlines", []),
                                descriptions_json=ad.get("descriptions", []),
                                final_urls_json=ad.get("final_urls", []),
                                status=ad["status"],
                            )
                            db.add(ad_obj)
                        else:
                            ad_obj.headlines_json = ad.get("headlines", [])
                            ad_obj.descriptions_json = ad.get("descriptions", [])
                            ad_obj.final_urls_json = ad.get("final_urls", [])
                            ad_obj.status = ad["status"]
                        total_ad += 1

                await db.flush()

            await _update_sync_progress(
                db, integration, "syncing",
                f"Synced {total_ag} ad groups, {total_kw} keywords, {total_ad} ads",
                55,
            )

            # Step 5: Conversion actions (skipped during lightweight sync)
            conv_count = 0
            if full_sync:
                await _update_sync_progress(db, integration, "syncing", "Pulling conversion actions...", 60)
                conv_actions = await client.get_conversion_actions()
            else:
                await _update_sync_progress(db, integration, "syncing", "Lightweight sync — skipping conversion actions", 60)
                conv_actions = []
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
                conv_count += 1
            await _update_sync_progress(
                db, integration, "syncing",
                f"Synced {conv_count} conversion actions",
                70, conversions_synced=conv_count,
            )

            # Step 6: Performance metrics — upsert by (tenant, campaign_id, date)
            await _update_sync_progress(db, integration, "syncing", f"Pulling {date_range} performance data...", 75)
            metrics = await client.get_performance_metrics(date_range)
            metrics_count = 0
            for m in metrics:
                # Use google campaign_id as entity_id so dashboard joins work
                google_cid = m["campaign_id"]
                existing_perf = await db.execute(
                    select(PerformanceDaily).where(
                        PerformanceDaily.tenant_id == tenant_id,
                        PerformanceDaily.entity_type == "campaign",
                        PerformanceDaily.entity_id == google_cid,
                        PerformanceDaily.date == m["date"],
                    )
                )
                perf = existing_perf.scalar_one_or_none()
                if not perf:
                    perf = PerformanceDaily(
                        tenant_id=tenant_id,
                        entity_type="campaign",
                        entity_id=google_cid,
                        date=m["date"],
                    )
                    db.add(perf)
                perf.impressions = m.get("impressions", 0)
                perf.clicks = m.get("clicks", 0)
                perf.cost_micros = m.get("cost_micros", 0)
                perf.conversions = m.get("conversions", 0)
                perf.conv_value = m.get("conv_value", 0)
                perf.ctr = m.get("ctr", 0)
                perf.cpc_micros = m.get("avg_cpc", 0)
                metrics_count += 1

            # Step 7: Keyword performance
            await _update_sync_progress(db, integration, "syncing", "Pulling keyword performance...", 78)
            kw_perf_count = 0
            try:
                kw_metrics = await client.get_keyword_performance(date_range)
                for km in kw_metrics:
                    existing_kp = await db.execute(
                        select(KeywordPerformanceDaily).where(
                            KeywordPerformanceDaily.tenant_id == tenant_id,
                            KeywordPerformanceDaily.keyword_id == km["keyword_id"],
                            KeywordPerformanceDaily.date == km["date"],
                        )
                    )
                    kp = existing_kp.scalar_one_or_none()
                    if not kp:
                        kp = KeywordPerformanceDaily(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            campaign_id=km["campaign_id"],
                            ad_group_id=km["ad_group_id"],
                            keyword_id=km["keyword_id"],
                            keyword_text=km.get("keyword_text", ""),
                            match_type=km.get("match_type"),
                            date=km["date"],
                        )
                        db.add(kp)
                    kp.impressions = km.get("impressions", 0)
                    kp.clicks = km.get("clicks", 0)
                    kp.cost_micros = km.get("cost_micros", 0)
                    kp.conversions = km.get("conversions", 0)
                    kp.conversion_value = km.get("conversion_value", 0)
                    kp.ctr = km.get("ctr", 0)
                    kp.average_cpc_micros = km.get("average_cpc_micros", 0)
                    kp.quality_score = km.get("quality_score")
                    kw_perf_count += 1
                await db.flush()
            except Exception as kp_err:
                logger.warning("Keyword performance sync failed", error=str(kp_err))

            # Step 8: Ad performance
            await _update_sync_progress(db, integration, "syncing", "Pulling ad performance...", 82)
            ad_perf_count = 0
            try:
                ad_metrics = await client.get_ad_performance(date_range)
                for am in ad_metrics:
                    existing_ap = await db.execute(
                        select(AdPerformanceDaily).where(
                            AdPerformanceDaily.tenant_id == tenant_id,
                            AdPerformanceDaily.ad_id == am["ad_id"],
                            AdPerformanceDaily.date == am["date"],
                        )
                    )
                    ap = existing_ap.scalar_one_or_none()
                    if not ap:
                        ap = AdPerformanceDaily(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            campaign_id=am["campaign_id"],
                            ad_group_id=am["ad_group_id"],
                            ad_id=am["ad_id"],
                            date=am["date"],
                        )
                        db.add(ap)
                    ap.impressions = am.get("impressions", 0)
                    ap.clicks = am.get("clicks", 0)
                    ap.cost_micros = am.get("cost_micros", 0)
                    ap.conversions = am.get("conversions", 0)
                    ap.conversion_value = am.get("conversion_value", 0)
                    ap.ctr = am.get("ctr", 0)
                    ap.average_cpc_micros = am.get("average_cpc_micros", 0)
                    ad_perf_count += 1
                await db.flush()
            except Exception as ap_err:
                logger.warning("Ad performance sync failed", error=str(ap_err))

            # Step 9: Ad group performance
            await _update_sync_progress(db, integration, "syncing", "Pulling ad group performance...", 85)
            ag_perf_count = 0
            try:
                ag_metrics = await client.get_ad_group_performance(date_range)
                for agm in ag_metrics:
                    existing_agp = await db.execute(
                        select(AdGroupPerformanceDaily).where(
                            AdGroupPerformanceDaily.tenant_id == tenant_id,
                            AdGroupPerformanceDaily.ad_group_id == agm["ad_group_id"],
                            AdGroupPerformanceDaily.date == agm["date"],
                        )
                    )
                    agp = existing_agp.scalar_one_or_none()
                    if not agp:
                        agp = AdGroupPerformanceDaily(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            campaign_id=agm["campaign_id"],
                            ad_group_id=agm["ad_group_id"],
                            date=agm["date"],
                        )
                        db.add(agp)
                    agp.impressions = agm.get("impressions", 0)
                    agp.clicks = agm.get("clicks", 0)
                    agp.cost_micros = agm.get("cost_micros", 0)
                    agp.conversions = agm.get("conversions", 0)
                    agp.conversion_value = agm.get("conversion_value", 0)
                    agp.ctr = agm.get("ctr", 0)
                    agp.average_cpc_micros = agm.get("average_cpc_micros", 0)
                    ag_perf_count += 1
                await db.flush()
            except Exception as agp_err:
                logger.warning("Ad group performance sync failed", error=str(agp_err))

            # Step 10: Search terms
            await _update_sync_progress(db, integration, "syncing", "Pulling search terms...", 88)
            st_count = 0
            try:
                search_terms = await client.get_search_terms(date_range)
                for st in search_terms:
                    existing_st = await db.execute(
                        select(SearchTermPerformance).where(
                            SearchTermPerformance.tenant_id == tenant_id,
                            SearchTermPerformance.search_term == st["search_term"],
                            SearchTermPerformance.campaign_id == st["campaign_id"],
                            SearchTermPerformance.date == st["date"],
                        )
                    )
                    stp = existing_st.scalar_one_or_none()
                    if not stp:
                        stp = SearchTermPerformance(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            campaign_id=st["campaign_id"],
                            ad_group_id=st["ad_group_id"],
                            keyword_id=st.get("keyword_id"),
                            keyword_text=st.get("keyword_text"),
                            search_term=st["search_term"],
                            date=st["date"],
                        )
                        db.add(stp)
                    stp.impressions = st.get("impressions", 0)
                    stp.clicks = st.get("clicks", 0)
                    stp.cost_micros = st.get("cost_micros", 0)
                    stp.conversions = st.get("conversions", 0)
                    stp.conversion_value = st.get("conversion_value", 0)
                    stp.ctr = st.get("ctr", 0)
                    stp.average_cpc_micros = st.get("average_cpc_micros", 0)
                    st_count += 1
                await db.flush()
            except Exception as st_err:
                logger.warning("Search terms sync failed", error=str(st_err))

            # Step 11: Landing pages
            await _update_sync_progress(db, integration, "syncing", "Pulling landing page data...", 91)
            lp_count = 0
            try:
                landing_pages = await client.get_landing_page_performance(date_range)
                for lp in landing_pages:
                    existing_lp = await db.execute(
                        select(LandingPagePerformance).where(
                            LandingPagePerformance.tenant_id == tenant_id,
                            LandingPagePerformance.landing_page_url == lp["landing_page_url"],
                            LandingPagePerformance.campaign_id == lp["campaign_id"],
                            LandingPagePerformance.date == lp["date"],
                        )
                    )
                    lpp = existing_lp.scalar_one_or_none()
                    if not lpp:
                        lpp = LandingPagePerformance(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            campaign_id=lp["campaign_id"],
                            ad_group_id=lp.get("ad_group_id"),
                            landing_page_url=lp["landing_page_url"],
                            date=lp["date"],
                        )
                        db.add(lpp)
                    lpp.impressions = lp.get("impressions", 0)
                    lpp.clicks = lp.get("clicks", 0)
                    lpp.cost_micros = lp.get("cost_micros", 0)
                    lpp.conversions = lp.get("conversions", 0)
                    lpp.conversion_value = lp.get("conversion_value", 0)
                    lpp.mobile_friendly_click_rate = lp.get("mobile_friendly_click_rate")
                    lpp.speed_score = lp.get("speed_score")
                    lp_count += 1
                await db.flush()
            except Exception as lp_err:
                logger.warning("Landing page sync failed", error=str(lp_err))

            # Step 12: Auction insights (skipped during lightweight sync — heavy + changes daily)
            ai_count = 0
            if full_sync:
                await _update_sync_progress(db, integration, "syncing", "Pulling auction insights...", 94)
            else:
                await _update_sync_progress(db, integration, "syncing", "Lightweight sync — skipping auction insights", 94)
            try:
                for c in (campaigns if full_sync else []):
                    insights = await client.get_auction_insights(c["campaign_id"])
                    camp_uuid = google_id_to_uuid.get(c["campaign_id"])
                    for ins in insights:
                        from datetime import datetime as dt_cls
                        ins_date = ins["date"]
                        if isinstance(ins_date, str):
                            ins_date = dt_cls.strptime(ins_date, "%Y-%m-%d").date()
                        existing_ai = await db.execute(
                            select(AuctionInsight).where(
                                AuctionInsight.tenant_id == tenant_id,
                                AuctionInsight.campaign_id == camp_uuid,
                                AuctionInsight.competitor_domain == ins["competitor_domain"],
                                AuctionInsight.date == ins_date,
                            )
                        )
                        ai_obj = existing_ai.scalar_one_or_none()
                        if not ai_obj:
                            ai_obj = AuctionInsight(
                                tenant_id=tenant_id,
                                campaign_id=camp_uuid,
                                date=ins_date,
                                competitor_domain=ins["competitor_domain"],
                            )
                            db.add(ai_obj)
                        ai_obj.impression_share = ins.get("impression_share", 0)
                        ai_obj.overlap_rate = ins.get("overlap_rate", 0)
                        ai_obj.outranking_share = ins.get("outranking_share", 0)
                        ai_obj.top_of_page_rate = ins.get("top_of_page_rate", 0)
                        ai_obj.abs_top_rate = ins.get("abs_top_rate", 0)
                        ai_obj.position_above_rate = ins.get("position_above_rate", 0)
                        ai_count += 1
                await db.flush()
            except Exception as ai_err:
                logger.warning("Auction insights sync failed", error=str(ai_err))

            # Step 13: Google recommendations (skipped during lightweight sync)
            rec_count = 0
            if full_sync:
                await _update_sync_progress(db, integration, "syncing", "Pulling Google recommendations...", 97)
                try:
                    g_recs = await client.get_google_recommendations()
                except Exception as rec_err:
                    g_recs = []
                    logger.warning("Google recommendations sync failed", error=str(rec_err))
            else:
                await _update_sync_progress(db, integration, "syncing", "Lightweight sync — skipping recommendations", 97)
                g_recs = []
            try:
                for gr in g_recs:
                    existing_gr = await db.execute(
                        select(GoogleRecommendation).where(
                            GoogleRecommendation.recommendation_resource_name == gr["resource_name"]
                        )
                    )
                    grobj = existing_gr.scalar_one_or_none()
                    if not grobj:
                        grobj = GoogleRecommendation(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            recommendation_resource_name=gr["resource_name"],
                            type=gr["type"],
                            campaign_id=gr.get("campaign_id"),
                            ad_group_id=gr.get("ad_group_id"),
                            impact_base_metrics=gr.get("impact_base", {}),
                            impact_potential_metrics=gr.get("impact_potential", {}),
                            details=gr.get("details", {}),
                        )
                        db.add(grobj)
                    else:
                        grobj.impact_base_metrics = gr.get("impact_base", {})
                        grobj.impact_potential_metrics = gr.get("impact_potential", {})
                        grobj.details = gr.get("details", {})
                        grobj.synced_at = datetime.now(timezone.utc)
                    rec_count += 1
                await db.flush()
            except Exception as rec_upsert_err:
                logger.warning("Google recommendations upsert failed", error=str(rec_upsert_err))

            # Step 14: LSA leads + conversations
            await _update_sync_progress(db, integration, "syncing", "Pulling Local Services leads...", 98)
            lsa_lead_count = 0
            lsa_conv_count = 0
            try:
                lsa_leads = await client.get_lsa_leads(days=30)
                # Build a mapping: lead_resource_name -> our LSALead UUID
                lsa_resource_to_uuid = {}
                for ll in lsa_leads:
                    existing_ll = await db.execute(
                        select(LSALead).where(
                            LSALead.tenant_id == tenant_id,
                            LSALead.google_lead_id == ll["lead_id"],
                        )
                    )
                    lead_obj = existing_ll.scalar_one_or_none()
                    if not lead_obj:
                        lead_obj = LSALead(
                            tenant_id=tenant_id,
                            google_customer_id=integration.customer_id,
                            lead_resource_name=ll["resource_name"],
                            google_lead_id=ll["lead_id"],
                            lead_type=ll["lead_type"],
                            category_id=ll.get("category_id"),
                            service_id=ll.get("service_id"),
                            lead_status=ll.get("lead_status"),
                            locale=ll.get("locale"),
                            contact_name=ll.get("contact_name"),
                            contact_phone=ll.get("contact_phone"),
                            contact_email=ll.get("contact_email"),
                            lead_charged=ll.get("lead_charged", False),
                            credit_state=ll.get("credit_state"),
                            lead_creation_datetime=ll.get("creation_date_time"),
                            synced_at=datetime.now(timezone.utc),
                        )
                        db.add(lead_obj)
                        await db.flush()
                    else:
                        lead_obj.lead_status = ll.get("lead_status") or lead_obj.lead_status
                        lead_obj.lead_charged = ll.get("lead_charged", lead_obj.lead_charged)
                        lead_obj.credit_state = ll.get("credit_state") or lead_obj.credit_state
                        lead_obj.contact_name = ll.get("contact_name") or lead_obj.contact_name
                        lead_obj.contact_phone = ll.get("contact_phone") or lead_obj.contact_phone
                        lead_obj.contact_email = ll.get("contact_email") or lead_obj.contact_email
                        lead_obj.synced_at = datetime.now(timezone.utc)
                    lsa_resource_to_uuid[ll["resource_name"]] = lead_obj.id
                    lsa_lead_count += 1
                await db.flush()

                # Conversations
                lsa_convos = await client.get_lsa_conversations(days=30)
                for lc in lsa_convos:
                    # Match conversation to its parent lead
                    lead_rn = lc.get("lead_resource_name", "")
                    parent_lead_uuid = lsa_resource_to_uuid.get(lead_rn)
                    if not parent_lead_uuid:
                        # Try to find lead in DB by resource name
                        lead_lookup = await db.execute(
                            select(LSALead).where(LSALead.lead_resource_name == lead_rn)
                        )
                        found_lead = lead_lookup.scalar_one_or_none()
                        if found_lead:
                            parent_lead_uuid = found_lead.id
                        else:
                            continue  # Skip orphan conversations

                    existing_lc = await db.execute(
                        select(LSAConversation).where(
                            LSAConversation.conversation_resource_name == lc["resource_name"],
                        )
                    )
                    conv_obj = existing_lc.scalar_one_or_none()
                    if not conv_obj:
                        conv_obj = LSAConversation(
                            tenant_id=tenant_id,
                            lead_id=parent_lead_uuid,
                            conversation_resource_name=lc["resource_name"],
                            channel=lc["channel"],
                            participant_type=lc.get("participant_type"),
                            event_datetime=lc.get("event_date_time"),
                            call_duration_ms=lc.get("call_duration_ms"),
                            call_recording_url=lc.get("call_recording_url"),
                            message_text=lc.get("message_text"),
                            attachment_urls=lc.get("attachment_urls"),
                            synced_at=datetime.now(timezone.utc),
                        )
                        db.add(conv_obj)
                    else:
                        conv_obj.call_recording_url = lc.get("call_recording_url") or conv_obj.call_recording_url
                        conv_obj.call_duration_ms = lc.get("call_duration_ms") or conv_obj.call_duration_ms
                        conv_obj.synced_at = datetime.now(timezone.utc)
                    lsa_conv_count += 1
                await db.flush()
            except Exception as lsa_err:
                logger.warning("LSA leads sync failed (account may not have LSA)", error=str(lsa_err))

            # Step 15: Complete
            integration.last_sync_at = datetime.now(timezone.utc)
            integration.health_score = 85
            await _update_sync_progress(
                db, integration, "completed",
                f"Sync complete — {campaign_count} campaigns, {total_ag} ad groups, {total_kw} keywords, "
                f"{total_ad} ads, {conv_count} conversions, {metrics_count} campaign metrics, "
                f"{kw_perf_count} keyword metrics, {ad_perf_count} ad metrics, {ag_perf_count} ad group metrics, "
                f"{st_count} search terms, {lp_count} landing pages, {ai_count} auction insights, "
                f"{rec_count} recommendations, {lsa_lead_count} LSA leads, {lsa_conv_count} LSA conversations",
                100,
            )
            logger.info("Ads account sync complete", tenant_id=tenant_id, integration_id=integration_id,
                        campaigns=campaign_count, ad_groups=total_ag, keywords=total_kw,
                        ads=total_ad, conversions=conv_count, metrics=metrics_count,
                        kw_perf=kw_perf_count, ad_perf=ad_perf_count, ag_perf=ag_perf_count,
                        search_terms=st_count, landing_pages=lp_count, auction_insights=ai_count,
                        recommendations=rec_count, lsa_leads=lsa_lead_count, lsa_conversations=lsa_conv_count)
        except Exception as e:
            await db.rollback()
            # Extract real error from RetryError wrapper
            real_error = e
            if isinstance(e, RetryError) and e.last_attempt and e.last_attempt.exception():
                real_error = e.last_attempt.exception()
            error_msg = str(real_error)
            # Re-fetch integration to update error status
            async with task_session_factory() as err_db:
                res = await err_db.execute(
                    select(IntegrationGoogleAds).where(IntegrationGoogleAds.id == integration_id)
                )
                integ = res.scalar_one_or_none()
                if integ:
                    integ.sync_status = "failed"
                    integ.sync_message = f"Sync failed: {error_msg[:400]}"
                    integ.sync_progress = 0
                    integ.sync_error = error_msg[:1000]
                    await err_db.commit()
            logger.error("Ads account sync failed", tenant_id=tenant_id, error=error_msg)

    await task_engine.dispose()


@celery_app.task(name="app.jobs.tasks.launch_campaign_task")
def launch_campaign_task(tenant_id: str, campaign_id: str, actor_id: str):
    import asyncio
    asyncio.run(_launch_campaign_async(tenant_id, campaign_id, actor_id))


async def _launch_campaign_async(tenant_id: str, campaign_id: str, actor_id: str):
    """
    Full campaign launch pipeline:
      1. Create campaign + budget in Google Ads (PAUSED)
      2. Create ad groups from settings_json.ad_groups
      3. Create keywords per ad group
      4. Create RSA ads per ad group
      5. Add campaign-level negative keywords
      6. Enable campaign
      7. Log change for rollback
    """
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
            campaign.settings_json = {**(campaign.settings_json or {}), "launch_error": "No active Google Ads integration"}
            await db.commit()
            return

        settings = campaign.settings_json or {}
        ad_groups_data = settings.get("ad_groups", [])
        launch_log = {"steps": []}

        try:
            client = GoogleAdsClient(
                customer_id=integration.customer_id,
                refresh_token_encrypted=integration.refresh_token_encrypted,
                login_customer_id=integration.login_customer_id,
            )

            # ── Step 1: Create campaign + budget (PAUSED) ──
            campaign_result = await client.create_campaign({
                "name": campaign.name,
                "budget_micros": campaign.budget_micros,
                "channel_type": campaign.type or "SEARCH",
                "bidding_strategy": campaign.bidding_strategy or "MAXIMIZE_CONVERSIONS",
                "network": settings.get("network", "SEARCH"),
            })

            if campaign_result.get("status") != "created":
                campaign.status = "FAILED"
                campaign.settings_json = {**settings, "launch_error": campaign_result.get("error", "Campaign creation failed")}
                await db.commit()
                return

            campaign_resource = campaign_result["campaign_resource"]
            google_campaign_id = campaign_result["campaign_id"]
            campaign.campaign_id = google_campaign_id
            launch_log["steps"].append({"step": "campaign", "status": "created", "resource": campaign_resource})
            logger.info("Campaign created in Google Ads", campaign_resource=campaign_resource)

            # ── Step 2: Create ad groups → keywords → ads ──
            ag_created = 0
            kw_created = 0
            ad_created = 0

            for ag_data in ad_groups_data:
                ag_name = ag_data.get("name", f"Ad Group {ag_created + 1}")

                ag_result = await client.create_ad_group(campaign_resource, {"name": ag_name})
                if ag_result.get("status") != "created":
                    launch_log["steps"].append({"step": "ad_group", "name": ag_name, "status": "failed", "error": ag_result.get("error")})
                    logger.warning("Ad group creation failed", name=ag_name, error=ag_result.get("error"))
                    continue

                ag_resource = ag_result["ad_group_resource"]
                ag_created += 1
                launch_log["steps"].append({"step": "ad_group", "name": ag_name, "status": "created"})

                # ── Step 2a: Keywords for this ad group ──
                keywords = ag_data.get("keywords", [])
                if keywords:
                    kw_result = await client.create_keywords(ag_resource, keywords)
                    count = kw_result.get("created", 0)
                    kw_created += count
                    launch_log["steps"].append({"step": "keywords", "ad_group": ag_name, "count": count, "status": kw_result.get("status")})

                # ── Step 2b: RSA ads for this ad group ──
                ads = ag_data.get("ads", [])
                for ad_data in ads:
                    ad_result = await client.create_responsive_search_ad(ag_resource, ad_data)
                    if ad_result.get("status") == "created":
                        ad_created += 1
                    launch_log["steps"].append({"step": "rsa", "ad_group": ag_name, "status": ad_result.get("status")})

            # ── Step 3: Campaign-level negative keywords ──
            neg_created = 0
            # Collect negatives from all ad groups (they're typically the same list)
            all_negatives = set()
            for ag_data in ad_groups_data:
                for neg in ag_data.get("negatives", []):
                    neg_text = neg.get("text", neg) if isinstance(neg, dict) else str(neg)
                    if neg_text:
                        all_negatives.add(neg_text)

            if all_negatives and google_campaign_id:
                neg_result = await client.add_negative_keywords(google_campaign_id, list(all_negatives))
                neg_created = neg_result.get("count", 0)
                launch_log["steps"].append({"step": "negatives", "count": neg_created, "status": neg_result.get("status")})

            # ── Step 4: Enable campaign ──
            enable_result = await client.update_campaign_status(campaign_resource, "ENABLED")
            launch_log["steps"].append({"step": "enable", "status": enable_result.get("status")})

            # ── Update local campaign record ──
            campaign.status = "ENABLED"
            campaign.is_draft = False
            campaign.settings_json = {
                **settings,
                "launch_log": launch_log,
                "google_campaign_resource": campaign_resource,
                "ad_groups_created": ag_created,
                "keywords_created": kw_created,
                "ads_created": ad_created,
                "negatives_created": neg_created,
            }

            log = ChangeLog(
                tenant_id=tenant_id,
                actor_type="user",
                actor_id=actor_id,
                google_customer_id=campaign.google_customer_id,
                entity_type="campaign",
                entity_id=campaign_id,
                before_json={"status": "DRAFT"},
                after_json={
                    "status": "ENABLED",
                    "google_campaign_id": google_campaign_id,
                    "ad_groups": ag_created,
                    "keywords": kw_created,
                    "ads": ad_created,
                    "negatives": neg_created,
                },
                reason="Campaign launched via approval flow",
                rollback_token=str(uuid.uuid4()),
            )
            db.add(log)
            await db.commit()

            logger.info("Campaign launch complete",
                        campaign_id=campaign_id,
                        google_campaign_id=google_campaign_id,
                        ad_groups=ag_created,
                        keywords=kw_created,
                        ads=ad_created,
                        negatives=neg_created)

        except Exception as e:
            campaign.status = "FAILED"
            campaign.settings_json = {**settings, "launch_error": str(e), "launch_log": launch_log}
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
    from app.services.email_service import send_tenant_weekly_report
    from app.models.tenant import Tenant

    async with async_session_factory() as db:
        svc = ReportService(db, tenant_id)
        report = await svc.generate_weekly_report(period_days)
        logger.info("Report generated", tenant_id=tenant_id, type=report_type)

        # Send email if weekly report
        if report_type == "weekly":
            tenant = await db.get(Tenant, tenant_id)
            biz_name = tenant.name if tenant else "Your Business"
            period_str = report.get("period", {}).get("start", "") + " — " + report.get("period", {}).get("end", "")
            kpis = report.get("kpis", {}).get("current", {})
            changes = report.get("kpis", {}).get("changes", {})
            metrics = {}
            if kpis.get("cost"):
                cost_delta = f" ({changes.get('cost', 0):+.1f}%)" if changes.get("cost") else ""
                metrics["Spend"] = f"${kpis['cost']:,.2f}{cost_delta}"
            if kpis.get("conversions"):
                conv_delta = f" ({changes.get('conversions', 0):+.1f}%)" if changes.get("conversions") else ""
                metrics["Conversions"] = f"{kpis['conversions']:.0f}{conv_delta}"
            if kpis.get("conv_value"):
                metrics["Revenue"] = f"${kpis['conv_value']:,.2f}"
            if kpis.get("cpa"):
                cpa_delta = f" ({changes.get('cpa', 0):+.1f}%)" if changes.get("cpa") else ""
                metrics["Cost per Lead"] = f"${kpis['cpa']:,.2f}{cpa_delta}"
            if kpis.get("clicks"):
                metrics["Clicks"] = f"{kpis['clicks']:,}"
            if kpis.get("ctr"):
                metrics["CTR"] = f"{kpis['ctr']:.2f}%"

            highlights = report.get("wins", []) + report.get("next_week_focus", [])

            result = await send_tenant_weekly_report(
                db=db, tenant_id=tenant_id,
                business_name=biz_name, period=period_str,
                metrics=metrics, highlights=highlights[:5],
            )
            logger.info("Weekly email result", tenant_id=tenant_id, result=result)


@celery_app.task(name="app.jobs.tasks.start_experiment_task")
def start_experiment_task(tenant_id: str, experiment_id: str):
    import asyncio
    asyncio.run(_start_experiment(tenant_id, experiment_id))


async def _start_experiment(tenant_id: str, experiment_id: str):
    from app.core.database import async_session_factory
    from app.models.experiment import Experiment
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.integrations.google_ads.client import GoogleAdsClient

    async with async_session_factory() as db:
        exp = await db.get(Experiment, experiment_id)
        if not exp or exp.tenant_id != tenant_id:
            logger.error("Experiment not found", experiment_id=experiment_id)
            return

        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            exp.status = "failed"
            exp.results_json = {"error": "No Google Ads integration"}
            await db.commit()
            return

        client = GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
            login_customer_id=integration.login_customer_id,
        )

        # Get campaign_id from entity_scope
        campaign_id = (exp.entity_scope_json or {}).get("campaign_id")
        if not campaign_id:
            exp.status = "failed"
            exp.results_json = {"error": "No campaign_id in entity_scope"}
            await db.commit()
            return

        # Create experiment in Google Ads
        result = await client.create_experiment(
            name=exp.name,
            campaign_id=campaign_id,
            suffix="exp",
            traffic_split_pct=50,
        )

        if result.get("status") == "error":
            exp.status = "failed"
            exp.results_json = {"error": result.get("error")}
            await db.commit()
            return

        # Schedule the experiment
        exp_resource = result.get("experiment_resource")
        schedule_result = await client.schedule_experiment(exp_resource)

        exp.status = "running"
        exp.results_json = {
            "google_experiment_resource": exp_resource,
            "google_draft_resource": result.get("draft_resource"),
            "schedule_status": schedule_result.get("status"),
        }
        await db.commit()
        logger.info("Experiment started in Google Ads", experiment_id=experiment_id, resource=exp_resource)


@celery_app.task(name="app.jobs.tasks.promote_experiment_winner_task")
def promote_experiment_winner_task(tenant_id: str, experiment_id: str, variant_index: int):
    import asyncio
    asyncio.run(_promote_experiment(tenant_id, experiment_id, variant_index))


async def _promote_experiment(tenant_id: str, experiment_id: str, variant_index: int):
    from app.core.database import async_session_factory
    from app.models.experiment import Experiment
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.integrations.google_ads.client import GoogleAdsClient

    async with async_session_factory() as db:
        exp = await db.get(Experiment, experiment_id)
        if not exp or exp.tenant_id != tenant_id:
            logger.error("Experiment not found", experiment_id=experiment_id)
            return

        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            return

        client = GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
            login_customer_id=integration.login_customer_id,
        )

        exp_resource = (exp.results_json or {}).get("google_experiment_resource")
        if not exp_resource:
            exp.results_json = {**(exp.results_json or {}), "promote_error": "No experiment resource found"}
            await db.commit()
            return

        # Get final results before promoting
        results = await client.get_experiment_results(exp_resource)

        # Promote the experiment
        promote_result = await client.promote_experiment(exp_resource)

        exp.status = "completed"
        exp.results_json = {
            **(exp.results_json or {}),
            "arms": results.get("arms", []),
            "promoted_variant": variant_index,
            "promote_status": promote_result.get("status"),
        }
        await db.commit()
        logger.info("Experiment promoted", experiment_id=experiment_id)


@celery_app.task(name="app.jobs.tasks.collect_experiment_results_task")
def collect_experiment_results_task(tenant_id: str, experiment_id: str):
    """Periodic task to collect experiment metrics from Google Ads."""
    import asyncio
    asyncio.run(_collect_experiment_results(tenant_id, experiment_id))


async def _collect_experiment_results(tenant_id: str, experiment_id: str):
    from app.core.database import async_session_factory
    from app.models.experiment import Experiment
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.integrations.google_ads.client import GoogleAdsClient

    async with async_session_factory() as db:
        exp = await db.get(Experiment, experiment_id)
        if not exp or exp.status != "running":
            return

        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            return

        client = GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
            login_customer_id=integration.login_customer_id,
        )

        exp_resource = (exp.results_json or {}).get("google_experiment_resource")
        if not exp_resource:
            return

        results = await client.get_experiment_results(exp_resource)
        exp.results_json = {
            **(exp.results_json or {}),
            "arms": results.get("arms", []),
            "experiment_status": results.get("experiment", {}).get("status"),
            "last_collected": datetime.now(timezone.utc).isoformat(),
        }
        await db.commit()
        logger.info("Experiment results collected", experiment_id=experiment_id)


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
            sync_ads_account_task.delay(integration.tenant_id, integration.id, full_sync=False)
        logger.info("Hourly lightweight sync dispatched", count=len(integrations))


@celery_app.task(name="app.jobs.tasks.sync_all_ads_daily")
def sync_all_ads_daily():
    import asyncio
    asyncio.run(_sync_all_daily())


async def _sync_all_daily():
    from app.core.database import async_session_factory
    from app.models.integration_google_ads import IntegrationGoogleAds

    async with async_session_factory() as db:
        result = await db.execute(
            select(IntegrationGoogleAds).where(IntegrationGoogleAds.is_active == True)
        )
        integrations = result.scalars().all()
        for integration in integrations:
            sync_ads_account_task.delay(integration.tenant_id, integration.id, full_sync=True)
        logger.info("Daily full sync dispatched", count=len(integrations))


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


# ── LSA Auto-Dispute ──────────────────────────────────────────

@celery_app.task(name="app.jobs.tasks.auto_dispute_lsa_leads")
def auto_dispute_lsa_leads():
    """Auto-dispute charged LSA leads that AI flagged as spam/unqualified."""
    import asyncio
    asyncio.run(_auto_dispute_lsa_leads_async())


async def _auto_dispute_lsa_leads_async():
    from app.core.database import async_session_factory
    from app.models.lsa_lead import LSALead
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.integrations.google_ads.client import GoogleAdsClient
    from datetime import datetime, timezone, timedelta

    async with async_session_factory() as db:
        # Find charged leads with low AI quality score and not yet disputed
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        result = await db.execute(
            select(LSALead).where(
                and_(
                    LSALead.lead_charged == True,
                    LSALead.ai_qualified_lead == False,
                    LSALead.ai_lead_quality_score.isnot(None),
                    LSALead.ai_lead_quality_score < 20,
                    LSALead.credit_state.in_([None, "NORMAL"]),
                    LSALead.feedback_submitted_at.is_(None),
                    LSALead.lead_creation_datetime >= cutoff,
                )
            )
        )
        leads = result.scalars().all()

        if not leads:
            logger.info("LSA auto-dispute: no eligible leads found")
            return

        logger.info("LSA auto-dispute: found eligible leads", count=len(leads))

        # Group leads by google_customer_id so we can reuse clients
        leads_by_customer = {}
        for lead in leads:
            cid = lead.google_customer_id
            if cid not in leads_by_customer:
                leads_by_customer[cid] = []
            leads_by_customer[cid].append(lead)

        disputed = 0
        failed = 0

        for customer_id, customer_leads in leads_by_customer.items():
            # Find active integration for this customer
            integ_result = await db.execute(
                select(IntegrationGoogleAds).where(
                    IntegrationGoogleAds.customer_id == customer_id,
                    IntegrationGoogleAds.is_active == True,
                )
            )
            integration = integ_result.scalar_one_or_none()
            if not integration:
                logger.warning("LSA auto-dispute: no integration for customer", customer_id=customer_id)
                continue

            client = GoogleAdsClient(
                customer_id=integration.customer_id,
                refresh_token_encrypted=integration.refresh_token_encrypted,
                login_customer_id=integration.login_customer_id,
            )

            for lead in customer_leads:
                try:
                    # Determine dispute reason from AI analysis
                    reason = lead.ai_qualified_reason or "Spam or unrelated call"
                    if lead.ai_lead_quality_score is not None and lead.ai_lead_quality_score < 5:
                        feedback_type = "SPAM"
                    else:
                        feedback_type = "NOT_USEFUL"

                    await client.submit_lsa_lead_feedback(
                        lead.lead_resource_name,
                        feedback_type,
                    )

                    lead.credit_state = "CREDIT_REQUESTED"
                    lead.feedback_submitted_at = datetime.now(timezone.utc)
                    lead.feedback_data = {
                        "auto_disputed": True,
                        "feedback_type": feedback_type,
                        "reason": reason,
                        "ai_score": lead.ai_lead_quality_score,
                    }
                    disputed += 1
                    logger.info("LSA auto-dispute: disputed lead",
                                lead_id=str(lead.id), score=lead.ai_lead_quality_score)
                except Exception as e:
                    failed += 1
                    logger.error("LSA auto-dispute: failed to dispute lead",
                                 lead_id=str(lead.id), error=str(e))

        await db.commit()
        logger.info("LSA auto-dispute complete", disputed=disputed, failed=failed)
