"""
Account Scan Service — pulls all relevant Google Ads data and normalizes
into internal AccountSnapshot schema for the analysis engine.
"""
import structlog
from typing import Optional, List
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from app.core.config import settings
from app.services.operator.schemas import (
    AccountSnapshot, CampaignData, AdGroupData, KeywordData,
    SearchTermData, AdData, DeviceSegment, DayOfWeekSegment,
    HourOfDaySegment, GeoSegment, NegativeKeywordData,
)

logger = structlog.get_logger()


def _build_client(refresh_token: str, login_customer_id: Optional[str] = None) -> GoogleAdsClient:
    creds = {
        "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": settings.GOOGLE_ADS_CLIENT_ID,
        "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "use_proto_plus": True,
    }
    if login_customer_id:
        creds["login_customer_id"] = login_customer_id.replace("-", "")
    return GoogleAdsClient.load_from_dict(creds)


def _micros_to_currency(micros: int) -> float:
    return round(micros / 1_000_000, 2)


def _safe_div(a: float, b: float) -> float:
    return round(a / b, 4) if b > 0 else 0.0


async def collect_account_data(
    refresh_token: str,
    customer_id: str,
    date_start: str,
    date_end: str,
    campaign_ids: Optional[List[str]] = None,
    login_customer_id: Optional[str] = None,
) -> AccountSnapshot:
    """
    Pull all account data from Google Ads API and normalize into AccountSnapshot.
    """
    client = _build_client(refresh_token, login_customer_id=login_customer_id)
    ga_service = client.get_service("GoogleAdsService")
    cid = customer_id.replace("-", "")

    snapshot = AccountSnapshot(
        customer_id=cid,
        date_range_start=date_start,
        date_range_end=date_end,
    )

    campaign_filter = ""
    if campaign_ids:
        ids_str = ", ".join(f"'{c}'" for c in campaign_ids)
        campaign_filter = f" AND campaign.id IN ({ids_str})"

    try:
        # ── 1. Campaign-level data + metrics ─────────────────────────────
        snapshot.campaigns = await _fetch_campaigns(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 2. Ad Group-level data + metrics ─────────────────────────────
        snapshot.ad_groups = await _fetch_ad_groups(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 3. Keyword-level data + metrics ──────────────────────────────
        snapshot.keywords = await _fetch_keywords(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 4. Search terms ──────────────────────────────────────────────
        snapshot.search_terms = await _fetch_search_terms(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 5. Ads / assets ──────────────────────────────────────────────
        snapshot.ads = await _fetch_ads(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 6. Negative keywords ─────────────────────────────────────────
        snapshot.negatives = await _fetch_negatives(
            ga_service, cid, campaign_filter
        )

        # ── 7. Device segments ───────────────────────────────────────────
        snapshot.device_segments = await _fetch_device_segments(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 8. Day-of-week segments ──────────────────────────────────────
        snapshot.day_of_week_segments = await _fetch_day_of_week_segments(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 9. Hour-of-day segments ──────────────────────────────────────
        snapshot.hour_of_day_segments = await _fetch_hour_of_day_segments(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── 10. Geo segments ────────────────────────────────────────────
        snapshot.geo_segments = await _fetch_geo_segments(
            ga_service, cid, date_start, date_end, campaign_filter
        )

        # ── Compute totals ──────────────────────────────────────────────
        snapshot.total_spend = sum(c.cost for c in snapshot.campaigns)
        snapshot.total_conversions = sum(c.conversions for c in snapshot.campaigns)
        snapshot.total_clicks = sum(c.clicks for c in snapshot.campaigns)
        snapshot.total_impressions = sum(c.impressions for c in snapshot.campaigns)
        snapshot.total_conversion_value = sum(c.conversion_value for c in snapshot.campaigns)

        logger.info(
            "Account data collected",
            customer_id=cid,
            campaigns=len(snapshot.campaigns),
            ad_groups=len(snapshot.ad_groups),
            keywords=len(snapshot.keywords),
            search_terms=len(snapshot.search_terms),
            ads=len(snapshot.ads),
            total_spend=snapshot.total_spend,
        )

    except GoogleAdsException as ex:
        logger.error("Google Ads API error during scan", error=str(ex))
        raise
    except Exception as ex:
        logger.error("Unexpected error during account scan", error=str(ex))
        raise

    return snapshot


# ── Fetch helpers ────────────────────────────────────────────────────────────

async def _fetch_campaigns(ga_service, cid, date_start, date_end, campaign_filter) -> List[CampaignData]:
    query = f"""
        SELECT
            campaign.id, campaign.name, campaign.status,
            campaign.advertising_channel_type,
            campaign_budget.amount_micros,
            campaign.bidding_strategy_type,
            campaign.target_cpa.target_cpa_micros,
            campaign.start_date, campaign.end_date,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.conversions_value,
            metrics.ctr, metrics.average_cpc,
            metrics.cost_per_conversion,
            metrics.search_impression_share,
            metrics.search_top_impression_share,
            metrics.search_absolute_top_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share
        FROM campaign
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND campaign.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            c = row.campaign
            m = row.metrics
            cost = _micros_to_currency(m.cost_micros)
            results.append(CampaignData(
                campaign_id=str(c.id),
                name=c.name,
                status=c.status.name if hasattr(c.status, 'name') else str(c.status),
                campaign_type=str(c.advertising_channel_type.name) if hasattr(c.advertising_channel_type, 'name') else "",
                budget_amount_micros=row.campaign_budget.amount_micros if row.campaign_budget else 0,
                budget_daily=_micros_to_currency(row.campaign_budget.amount_micros) if row.campaign_budget else 0.0,
                bidding_strategy=str(c.bidding_strategy_type.name) if hasattr(c.bidding_strategy_type, 'name') else "",
                target_cpa_micros=c.target_cpa.target_cpa_micros if hasattr(c, 'target_cpa') and c.target_cpa else None,
                start_date=c.start_date if c.start_date else None,
                end_date=c.end_date if c.end_date else None,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                cost=cost,
                conversions=round(m.conversions, 2),
                conversion_value=round(m.conversions_value, 2),
                ctr=round(m.ctr, 4),
                avg_cpc=_micros_to_currency(m.average_cpc),
                conv_rate=_safe_div(m.conversions, m.clicks),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
                roas=_safe_div(m.conversions_value, cost),
                search_impression_share=m.search_impression_share if m.search_impression_share else None,
                search_top_impression_share=m.search_top_impression_share if m.search_top_impression_share else None,
                search_abs_top_impression_share=m.search_absolute_top_impression_share if m.search_absolute_top_impression_share else None,
                search_lost_is_budget=m.search_budget_lost_impression_share if m.search_budget_lost_impression_share else None,
                search_lost_is_rank=m.search_rank_lost_impression_share if m.search_rank_lost_impression_share else None,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch campaigns", error=str(ex))
    return results


async def _fetch_ad_groups(ga_service, cid, date_start, date_end, campaign_filter) -> List[AdGroupData]:
    query = f"""
        SELECT
            ad_group.id, ad_group.name, ad_group.status,
            ad_group.campaign, ad_group.cpc_bid_micros,
            campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.conversions_value,
            metrics.ctr, metrics.average_cpc, metrics.cost_per_conversion
        FROM ad_group
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND ad_group.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            ag = row.ad_group
            m = row.metrics
            cost = _micros_to_currency(m.cost_micros)
            results.append(AdGroupData(
                ad_group_id=str(ag.id),
                campaign_id=str(row.campaign.id),
                name=ag.name,
                status=ag.status.name if hasattr(ag.status, 'name') else str(ag.status),
                cpc_bid_micros=ag.cpc_bid_micros if ag.cpc_bid_micros else None,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                cost=cost,
                conversions=round(m.conversions, 2),
                conversion_value=round(m.conversions_value, 2),
                ctr=round(m.ctr, 4),
                avg_cpc=_micros_to_currency(m.average_cpc),
                conv_rate=_safe_div(m.conversions, m.clicks),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch ad groups", error=str(ex))
    return results


async def _fetch_keywords(ga_service, cid, date_start, date_end, campaign_filter) -> List[KeywordData]:
    query = f"""
        SELECT
            ad_group_criterion.criterion_id,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            ad_group.id, campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.ctr, metrics.average_cpc,
            metrics.cost_per_conversion
        FROM keyword_view
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND ad_group_criterion.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            kw = row.ad_group_criterion
            m = row.metrics
            cost = _micros_to_currency(m.cost_micros)
            results.append(KeywordData(
                keyword_id=str(kw.criterion_id),
                ad_group_id=str(row.ad_group.id),
                campaign_id=str(row.campaign.id),
                text=kw.keyword.text,
                match_type=kw.keyword.match_type.name if hasattr(kw.keyword.match_type, 'name') else str(kw.keyword.match_type),
                status=kw.status.name if hasattr(kw.status, 'name') else str(kw.status),
                quality_score=kw.quality_info.quality_score if hasattr(kw, 'quality_info') and kw.quality_info and kw.quality_info.quality_score else None,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                cost=cost,
                conversions=round(m.conversions, 2),
                ctr=round(m.ctr, 4),
                avg_cpc=_micros_to_currency(m.average_cpc),
                conv_rate=_safe_div(m.conversions, m.clicks),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch keywords", error=str(ex))
    return results


async def _fetch_search_terms(ga_service, cid, date_start, date_end, campaign_filter) -> List[SearchTermData]:
    query = f"""
        SELECT
            search_term_view.search_term,
            campaign.id, ad_group.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.ctr, metrics.cost_per_conversion
        FROM search_term_view
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            m = row.metrics
            cost = _micros_to_currency(m.cost_micros)
            results.append(SearchTermData(
                search_term=row.search_term_view.search_term,
                campaign_id=str(row.campaign.id),
                ad_group_id=str(row.ad_group.id),
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                cost=cost,
                conversions=round(m.conversions, 2),
                ctr=round(m.ctr, 4),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch search terms", error=str(ex))
    return results


async def _fetch_ads(ga_service, cid, date_start, date_end, campaign_filter) -> List[AdData]:
    query = f"""
        SELECT
            ad_group_ad.ad.id, ad_group_ad.ad.type,
            ad_group_ad.ad.responsive_search_ad.headlines,
            ad_group_ad.ad.responsive_search_ad.descriptions,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad_strength,
            ad_group.id, campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.ctr, metrics.cost_per_conversion
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND ad_group_ad.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            ad = row.ad_group_ad.ad
            m = row.metrics
            cost = _micros_to_currency(m.cost_micros)

            headlines = []
            descriptions = []
            if hasattr(ad, 'responsive_search_ad') and ad.responsive_search_ad:
                rsa = ad.responsive_search_ad
                headlines = [h.text for h in rsa.headlines] if rsa.headlines else []
                descriptions = [d.text for d in rsa.descriptions] if rsa.descriptions else []

            final_url = ad.final_urls[0] if ad.final_urls else None

            results.append(AdData(
                ad_id=str(ad.id),
                ad_group_id=str(row.ad_group.id),
                campaign_id=str(row.campaign.id),
                ad_type=ad.type_.name if hasattr(ad.type_, 'name') else str(ad.type_),
                headlines=headlines,
                descriptions=descriptions,
                final_url=final_url,
                ad_strength=row.ad_group_ad.ad_strength.name if hasattr(row.ad_group_ad.ad_strength, 'name') else None,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                cost=cost,
                conversions=round(m.conversions, 2),
                ctr=round(m.ctr, 4),
                conv_rate=_safe_div(m.conversions, m.clicks),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch ads", error=str(ex))
    return results


async def _fetch_negatives(ga_service, cid, campaign_filter) -> List[NegativeKeywordData]:
    results = []
    # Campaign-level negatives
    query = f"""
        SELECT
            campaign_criterion.keyword.text,
            campaign_criterion.keyword.match_type,
            campaign.id
        FROM campaign_criterion
        WHERE campaign_criterion.type = 'KEYWORD'
            AND campaign_criterion.negative = TRUE
            {campaign_filter}
    """
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            kw = row.campaign_criterion.keyword
            results.append(NegativeKeywordData(
                keyword_text=kw.text,
                match_type=kw.match_type.name if hasattr(kw.match_type, 'name') else str(kw.match_type),
                level="campaign",
                parent_id=str(row.campaign.id),
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch campaign negatives", error=str(ex))
    return results


async def _fetch_device_segments(ga_service, cid, date_start, date_end, campaign_filter) -> List[DeviceSegment]:
    query = f"""
        SELECT
            segments.device, campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.ctr, metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND campaign.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            m = row.metrics
            cost = _micros_to_currency(m.cost_micros)
            results.append(DeviceSegment(
                device=row.segments.device.name if hasattr(row.segments.device, 'name') else str(row.segments.device),
                campaign_id=str(row.campaign.id),
                impressions=m.impressions,
                clicks=m.clicks,
                cost=cost,
                conversions=round(m.conversions, 2),
                ctr=round(m.ctr, 4),
                conv_rate=_safe_div(m.conversions, m.clicks),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch device segments", error=str(ex))
    return results


async def _fetch_day_of_week_segments(ga_service, cid, date_start, date_end, campaign_filter) -> List[DayOfWeekSegment]:
    query = f"""
        SELECT
            segments.day_of_week, campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND campaign.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            m = row.metrics
            results.append(DayOfWeekSegment(
                day_of_week=row.segments.day_of_week.name if hasattr(row.segments.day_of_week, 'name') else str(row.segments.day_of_week),
                campaign_id=str(row.campaign.id),
                impressions=m.impressions,
                clicks=m.clicks,
                cost=_micros_to_currency(m.cost_micros),
                conversions=round(m.conversions, 2),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch day-of-week segments", error=str(ex))
    return results


async def _fetch_hour_of_day_segments(ga_service, cid, date_start, date_end, campaign_filter) -> List[HourOfDaySegment]:
    query = f"""
        SELECT
            segments.hour, campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            AND campaign.status != 'REMOVED'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            m = row.metrics
            results.append(HourOfDaySegment(
                hour=row.segments.hour,
                campaign_id=str(row.campaign.id),
                impressions=m.impressions,
                clicks=m.clicks,
                cost=_micros_to_currency(m.cost_micros),
                conversions=round(m.conversions, 2),
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch hour-of-day segments", error=str(ex))
    return results


async def _fetch_geo_segments(ga_service, cid, date_start, date_end, campaign_filter) -> List[GeoSegment]:
    query = f"""
        SELECT
            geographic_view.country_criterion_id,
            geographic_view.location_type,
            campaign.id,
            metrics.impressions, metrics.clicks, metrics.cost_micros,
            metrics.conversions, metrics.cost_per_conversion
        FROM geographic_view
        WHERE segments.date BETWEEN '{date_start}' AND '{date_end}'
            {campaign_filter}
    """
    results = []
    try:
        response = ga_service.search(customer_id=cid, query=query)
        for row in response:
            m = row.metrics
            geo = row.geographic_view
            results.append(GeoSegment(
                location_name=str(geo.country_criterion_id),
                location_id=str(geo.country_criterion_id),
                campaign_id=str(row.campaign.id),
                impressions=m.impressions,
                clicks=m.clicks,
                cost=_micros_to_currency(m.cost_micros),
                conversions=round(m.conversions, 2),
                cost_per_conversion=round(m.cost_per_conversion, 2) if m.cost_per_conversion else 0.0,
            ))
    except GoogleAdsException as ex:
        logger.warning("Failed to fetch geo segments", error=str(ex))
    return results
