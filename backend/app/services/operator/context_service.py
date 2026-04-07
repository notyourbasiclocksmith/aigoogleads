"""
Google Ads Context Service — reads live account data and normalizes it for Claude.

Builds a concise but complete context payload that Claude can analyze.
"""
from typing import Dict, Any, List, Optional
import structlog
from app.integrations.google_ads.client import GoogleAdsClient

logger = structlog.get_logger()


class GoogleAdsContextService:
    """Reads Google Ads data and produces a normalized context payload for Claude."""

    def __init__(self, ads_client: GoogleAdsClient):
        self.client = ads_client

    async def build_full_context(self, date_range: str = "LAST_30_DAYS") -> Dict[str, Any]:
        """Build complete account context for Claude analysis."""
        logger.info("Building full account context", customer_id=self.client.customer_id)

        account_info = await self.client.get_account_info()
        campaigns = await self.client.get_campaigns()
        perf = await self._get_campaign_performance(date_range)
        keyword_data = await self._get_all_keyword_performance(date_range)
        search_terms = await self._get_search_term_report(date_range)
        ad_data = await self._get_all_ad_performance(date_range)

        # Conversion tracking setup
        try:
            conversion_actions = await self.client.get_conversion_actions()
        except Exception as e:
            logger.warning("Failed to get conversion actions", error=str(e))
            conversion_actions = []

        # Extensions, geo targeting, device bid modifiers
        extensions_data = await self._get_existing_extensions(date_range)
        geo_data = await self._get_geo_targeting()
        device_data = await self._get_device_bid_modifiers()

        # Compute heuristics
        heuristics = self._compute_heuristics(perf, keyword_data, search_terms, ad_data)

        context = {
            "account": account_info,
            "date_range": date_range,
            "campaigns": campaigns,
            "campaign_performance": perf,
            "keyword_performance": keyword_data,
            "search_terms": search_terms[:100],  # Top 100 by cost
            "ad_performance": ad_data,
            "conversion_actions": conversion_actions,
            "existing_extensions": extensions_data,
            "geo_targeting": geo_data,
            "device_bid_modifiers": device_data,
            "heuristics": heuristics,
        }
        logger.info("Context built", campaigns=len(campaigns), keywords=len(keyword_data), search_terms=len(search_terms))
        return context

    async def _get_campaign_performance(self, date_range: str) -> List[Dict[str, Any]]:
        """Get aggregated campaign-level performance."""
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    campaign.id, campaign.name, campaign.status,
                    campaign.bidding_strategy_type,
                    campaign_budget.amount_micros,
                    metrics.impressions, metrics.clicks, metrics.cost_micros,
                    metrics.conversions, metrics.conversions_value,
                    metrics.ctr, metrics.average_cpc,
                    metrics.cost_per_conversion,
                    metrics.search_impression_share
                FROM campaign
                WHERE campaign.status != 'REMOVED'
                    AND segments.date DURING {date_range}
            """
            response = ga_service.search(customer_id=self.client.customer_id, query=query)
            # Aggregate by campaign
            agg = {}
            for row in response:
                cid = str(row.campaign.id)
                if cid not in agg:
                    agg[cid] = {
                        "campaign_id": cid,
                        "name": row.campaign.name,
                        "status": row.campaign.status.name,
                        "bidding_strategy": row.campaign.bidding_strategy_type.name,
                        "daily_budget": round(row.campaign_budget.amount_micros / 1_000_000, 2),
                        "impressions": 0, "clicks": 0, "cost": 0,
                        "conversions": 0, "conv_value": 0,
                    }
                agg[cid]["impressions"] += row.metrics.impressions
                agg[cid]["clicks"] += row.metrics.clicks
                agg[cid]["cost"] += row.metrics.cost_micros / 1_000_000
                agg[cid]["conversions"] += row.metrics.conversions
                agg[cid]["conv_value"] += row.metrics.conversions_value

            # Compute derived metrics
            for c in agg.values():
                c["cost"] = round(c["cost"], 2)
                c["ctr"] = round(c["clicks"] / c["impressions"] * 100, 2) if c["impressions"] > 0 else 0
                c["avg_cpc"] = round(c["cost"] / c["clicks"], 2) if c["clicks"] > 0 else 0
                c["cost_per_conversion"] = round(c["cost"] / c["conversions"], 2) if c["conversions"] > 0 else 0
            return sorted(agg.values(), key=lambda x: x["cost"], reverse=True)
        except Exception as e:
            logger.error("Failed to get campaign performance", error=str(e))
            return []

    async def _get_all_keyword_performance(self, date_range: str) -> List[Dict[str, Any]]:
        """Get keyword-level performance across all campaigns."""
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    campaign.id, campaign.name,
                    ad_group.id, ad_group.name,
                    ad_group_criterion.criterion_id,
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    ad_group_criterion.status,
                    ad_group_criterion.quality_info.quality_score,
                    metrics.impressions, metrics.clicks, metrics.cost_micros,
                    metrics.conversions, metrics.ctr, metrics.average_cpc
                FROM keyword_view
                WHERE campaign.status != 'REMOVED'
                    AND ad_group.status != 'REMOVED'
                    AND ad_group_criterion.status != 'REMOVED'
                    AND segments.date DURING {date_range}
                ORDER BY metrics.cost_micros DESC
                LIMIT 200
            """
            response = ga_service.search(customer_id=self.client.customer_id, query=query)
            keywords = []
            for row in response:
                keywords.append({
                    "keyword_id": str(row.ad_group_criterion.criterion_id),
                    "text": row.ad_group_criterion.keyword.text,
                    "match_type": row.ad_group_criterion.keyword.match_type.name,
                    "status": row.ad_group_criterion.status.name,
                    "quality_score": row.ad_group_criterion.quality_info.quality_score or None,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                    "conversions": row.metrics.conversions,
                    "ctr": round(row.metrics.ctr * 100, 2),
                    "avg_cpc": round(row.metrics.average_cpc / 1_000_000, 2),
                })
            return keywords
        except Exception as e:
            logger.error("Failed to get keyword performance", error=str(e))
            return []

    async def _get_search_term_report(self, date_range: str) -> List[Dict[str, Any]]:
        """Get search term report for negative keyword opportunities."""
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    search_term_view.search_term,
                    campaign.id, campaign.name,
                    ad_group.id,
                    metrics.impressions, metrics.clicks, metrics.cost_micros,
                    metrics.conversions
                FROM search_term_view
                WHERE segments.date DURING {date_range}
                    AND metrics.cost_micros > 0
                ORDER BY metrics.cost_micros DESC
                LIMIT 150
            """
            response = ga_service.search(customer_id=self.client.customer_id, query=query)
            terms = []
            for row in response:
                terms.append({
                    "search_term": row.search_term_view.search_term,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "ad_group_id": str(row.ad_group.id),
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                    "conversions": row.metrics.conversions,
                    "ctr": round(row.metrics.clicks / row.metrics.impressions * 100, 2) if row.metrics.impressions > 0 else 0,
                })
            return terms
        except Exception as e:
            logger.error("Failed to get search terms", error=str(e))
            return []

    async def _get_all_ad_performance(self, date_range: str) -> List[Dict[str, Any]]:
        """Get ad-level performance."""
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT
                    campaign.id, campaign.name,
                    ad_group.id, ad_group.name,
                    ad_group_ad.ad.id,
                    ad_group_ad.ad.responsive_search_ad.headlines,
                    ad_group_ad.ad.responsive_search_ad.descriptions,
                    ad_group_ad.status, ad_group_ad.ad.final_urls,
                    ad_group_ad.ad_strength,
                    metrics.impressions, metrics.clicks, metrics.cost_micros,
                    metrics.conversions, metrics.ctr
                FROM ad_group_ad
                WHERE campaign.status != 'REMOVED'
                    AND ad_group_ad.status != 'REMOVED'
                    AND segments.date DURING {date_range}
                ORDER BY metrics.cost_micros DESC
                LIMIT 50
            """
            response = ga_service.search(customer_id=self.client.customer_id, query=query)
            ads = []
            for row in response:
                headlines = []
                descriptions = []
                try:
                    headlines = [h.text for h in row.ad_group_ad.ad.responsive_search_ad.headlines]
                    descriptions = [d.text for d in row.ad_group_ad.ad.responsive_search_ad.descriptions]
                except Exception:
                    pass
                ads.append({
                    "ad_id": str(row.ad_group_ad.ad.id),
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "ad_group_id": str(row.ad_group.id),
                    "ad_group_name": row.ad_group.name,
                    "headlines": headlines,
                    "descriptions": descriptions,
                    "final_urls": list(row.ad_group_ad.ad.final_urls),
                    "status": row.ad_group_ad.status.name,
                    "ad_strength": row.ad_group_ad.ad_strength.name if hasattr(row.ad_group_ad, "ad_strength") else None,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                    "conversions": row.metrics.conversions,
                    "ctr": round(row.metrics.ctr * 100, 2),
                })
            return ads
        except Exception as e:
            logger.error("Failed to get ad performance", error=str(e))
            return []

    async def _get_existing_extensions(self, date_range: str) -> List[Dict[str, Any]]:
        """Get sitelink, callout, and call assets linked to campaigns."""
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = """
                SELECT
                    campaign.id, campaign.name, campaign.status,
                    asset.id, asset.name, asset.type,
                    asset.sitelink_asset.link_text, asset.sitelink_asset.description1,
                    asset.callout_asset.callout_text,
                    asset.call_asset.phone_number
                FROM campaign_asset
                WHERE campaign.status != 'REMOVED'
            """
            response = ga_service.search(customer_id=self.client.customer_id, query=query)
            extensions = []
            for row in response:
                ext = {
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "asset_id": str(row.asset.id),
                    "asset_name": row.asset.name,
                    "asset_type": row.asset.type.name,
                }
                if row.asset.type.name == "SITELINK":
                    ext["link_text"] = row.asset.sitelink_asset.link_text
                    ext["description1"] = row.asset.sitelink_asset.description1
                elif row.asset.type.name == "CALLOUT":
                    ext["callout_text"] = row.asset.callout_asset.callout_text
                elif row.asset.type.name == "CALL":
                    ext["phone_number"] = row.asset.call_asset.phone_number
                extensions.append(ext)
            return extensions
        except Exception as e:
            logger.error("Failed to get existing extensions", error=str(e))
            return []

    async def _get_geo_targeting(self) -> List[Dict[str, Any]]:
        """Get location and proximity targeting for campaigns.

        GAQL does not support SQL-style parentheses in WHERE clauses, so we
        run two separate queries (LOCATION and PROXIMITY) and merge results.
        """
        geo_data: List[Dict[str, Any]] = []
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")

            # Query 1: LOCATION criteria
            loc_query = """
                SELECT
                    campaign.id, campaign.name, campaign.status,
                    campaign_criterion.location.geo_target_constant
                FROM campaign_criterion
                WHERE campaign.status != 'REMOVED'
                    AND campaign_criterion.type = 'LOCATION'
            """
            try:
                response = ga_service.search(customer_id=self.client.customer_id, query=loc_query)
                for row in response:
                    entry = {
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name,
                    }
                    if row.campaign_criterion.location.geo_target_constant:
                        entry["geo_target_constant"] = row.campaign_criterion.location.geo_target_constant
                    geo_data.append(entry)
            except Exception as e:
                logger.warning("Failed to get location criteria", error=str(e))

            # Query 2: PROXIMITY criteria
            prox_query = """
                SELECT
                    campaign.id, campaign.name, campaign.status,
                    campaign_criterion.proximity.geo_point.latitude_in_micro_degrees,
                    campaign_criterion.proximity.geo_point.longitude_in_micro_degrees,
                    campaign_criterion.proximity.radius
                FROM campaign_criterion
                WHERE campaign.status != 'REMOVED'
                    AND campaign_criterion.type = 'PROXIMITY'
            """
            try:
                response = ga_service.search(customer_id=self.client.customer_id, query=prox_query)
                for row in response:
                    entry = {
                        "campaign_id": str(row.campaign.id),
                        "campaign_name": row.campaign.name,
                    }
                    if row.campaign_criterion.proximity.geo_point.latitude_in_micro_degrees:
                        entry["latitude_micro"] = row.campaign_criterion.proximity.geo_point.latitude_in_micro_degrees
                        entry["longitude_micro"] = row.campaign_criterion.proximity.geo_point.longitude_in_micro_degrees
                        entry["radius"] = row.campaign_criterion.proximity.radius
                    geo_data.append(entry)
            except Exception as e:
                logger.warning("Failed to get proximity criteria", error=str(e))

            return geo_data
        except Exception as e:
            logger.error("Failed to get geo targeting", error=str(e))
            return []

    async def _get_device_bid_modifiers(self) -> List[Dict[str, Any]]:
        """Get device-level bid modifiers for campaigns."""
        try:
            client = self.client._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = """
                SELECT
                    campaign.id, campaign.name, campaign.status,
                    campaign_criterion.device.type,
                    campaign_criterion.bid_modifier
                FROM campaign_criterion
                WHERE campaign.status != 'REMOVED'
                    AND campaign_criterion.type = 'DEVICE'
            """
            response = ga_service.search(customer_id=self.client.customer_id, query=query)
            devices = []
            for row in response:
                devices.append({
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "device_type": row.campaign_criterion.device.type.name,
                    "bid_modifier": row.campaign_criterion.bid_modifier,
                })
            return devices
        except Exception as e:
            logger.error("Failed to get device bid modifiers", error=str(e))
            return []

    def _compute_heuristics(
        self,
        campaign_perf: List[Dict],
        keywords: List[Dict],
        search_terms: List[Dict],
        ads: List[Dict],
    ) -> Dict[str, Any]:
        """Compute internal heuristics to help Claude prioritize."""
        wasted_keywords = [k for k in keywords if k["cost"] > 10 and k["conversions"] == 0]
        low_ctr_ads = [a for a in ads if a["impressions"] > 100 and a["ctr"] < 2.0]
        negative_opportunities = [t for t in search_terms if t["cost"] > 5 and t["conversions"] == 0]
        budget_limited = [c for c in campaign_perf if c.get("search_impression_share") and c.get("search_impression_share", 1) < 0.5]

        total_wasted = sum(k["cost"] for k in wasted_keywords)
        total_neg_waste = sum(t["cost"] for t in negative_opportunities)

        return {
            "wasted_keyword_count": len(wasted_keywords),
            "wasted_keyword_spend": round(total_wasted, 2),
            "low_ctr_ad_count": len(low_ctr_ads),
            "negative_keyword_opportunities": len(negative_opportunities),
            "negative_keyword_wasted_spend": round(total_neg_waste, 2),
            "budget_limited_campaigns": len(budget_limited),
            "total_keywords_analyzed": len(keywords),
            "total_search_terms_analyzed": len(search_terms),
            "total_ads_analyzed": len(ads),
        }
