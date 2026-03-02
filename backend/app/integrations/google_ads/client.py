"""
Google Ads API Client — Read + Write operations with rate limiting.

Capabilities:
- Read: account structure, campaigns, ad groups, ads, assets, keywords, negatives,
  performance metrics, conversions, auction insights
- Write (via changesets): create/update campaigns, ad groups, ads, keywords, negatives,
  assets; update bids/budgets/targeting; pause/enable entities
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.security import decrypt_token
from app.integrations.google_ads.oauth import refresh_access_token

logger = structlog.get_logger()


class GoogleAdsClient:
    """
    Wrapper around Google Ads API.
    In production, this uses the google-ads Python client library.
    Methods below show the integration pattern with pseudo-implementation.
    """

    def __init__(self, customer_id: str, refresh_token_encrypted: str, login_customer_id: Optional[str] = None):
        self.customer_id = customer_id
        self.login_customer_id = login_customer_id
        self._refresh_token = decrypt_token(refresh_token_encrypted)
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _ensure_token(self):
        if self._access_token and self._token_expires_at and datetime.now(timezone.utc) < self._token_expires_at:
            return
        tokens = await refresh_access_token(self._refresh_token)
        if tokens:
            self._access_token = tokens["access_token"]
            self._token_expires_at = datetime.now(timezone.utc)
        else:
            raise Exception("Failed to refresh Google Ads access token")

    def _get_client(self):
        """
        In production, instantiate google.ads.googleads.client.GoogleAdsClient
        using credentials. This is a placeholder for the integration pattern.
        """
        from google.ads.googleads.client import GoogleAdsClient as GAdsClient
        credentials = {
            "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            "client_id": settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
            "refresh_token": self._refresh_token,
            "use_proto_plus": True,
        }
        if self.login_customer_id:
            credentials["login_customer_id"] = self.login_customer_id
        return GAdsClient.load_from_dict(credentials)

    # ── READ OPERATIONS ──────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_account_info(self) -> Dict[str, Any]:
        await self._ensure_token()
        logger.info("Fetching account info", customer_id=self.customer_id)
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = """
                SELECT customer.id, customer.descriptive_name, customer.currency_code,
                       customer.time_zone, customer.manager
                FROM customer
                LIMIT 1
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            for row in response:
                return {
                    "customer_id": str(row.customer.id),
                    "name": row.customer.descriptive_name,
                    "currency": row.customer.currency_code,
                    "timezone": row.customer.time_zone,
                    "is_manager": row.customer.manager,
                }
        except Exception as e:
            logger.error("Failed to get account info", error=str(e))
            return {"customer_id": self.customer_id, "error": str(e)}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_campaigns(self) -> List[Dict[str, Any]]:
        await self._ensure_token()
        logger.info("Fetching campaigns", customer_id=self.customer_id)
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = """
                SELECT campaign.id, campaign.name, campaign.status,
                       campaign.advertising_channel_type, campaign.bidding_strategy_type,
                       campaign_budget.amount_micros
                FROM campaign
                WHERE campaign.status != 'REMOVED'
                ORDER BY campaign.id
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            campaigns = []
            for row in response:
                campaigns.append({
                    "campaign_id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "status": row.campaign.status.name,
                    "type": row.campaign.advertising_channel_type.name,
                    "bidding_strategy": row.campaign.bidding_strategy_type.name,
                    "budget_micros": row.campaign_budget.amount_micros,
                })
            return campaigns
        except Exception as e:
            logger.error("Failed to get campaigns", error=str(e))
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_ad_groups(self, campaign_id: str) -> List[Dict[str, Any]]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT ad_group.id, ad_group.name, ad_group.status,
                       ad_group.type
                FROM ad_group
                WHERE campaign.id = {campaign_id}
                  AND ad_group.status != 'REMOVED'
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            return [
                {
                    "ad_group_id": str(row.ad_group.id),
                    "name": row.ad_group.name,
                    "status": row.ad_group.status.name,
                    "type": row.ad_group.type_.name,
                }
                for row in response
            ]
        except Exception as e:
            logger.error("Failed to get ad groups", error=str(e))
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_keywords(self, ad_group_id: str) -> List[Dict[str, Any]]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT ad_group_criterion.criterion_id,
                       ad_group_criterion.keyword.text,
                       ad_group_criterion.keyword.match_type,
                       ad_group_criterion.status,
                       ad_group_criterion.quality_info.quality_score,
                       ad_group_criterion.effective_cpc_bid_micros
                FROM ad_group_criterion
                WHERE ad_group.id = {ad_group_id}
                  AND ad_group_criterion.type = 'KEYWORD'
                  AND ad_group_criterion.status != 'REMOVED'
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            return [
                {
                    "keyword_id": str(row.ad_group_criterion.criterion_id),
                    "text": row.ad_group_criterion.keyword.text,
                    "match_type": row.ad_group_criterion.keyword.match_type.name,
                    "status": row.ad_group_criterion.status.name,
                    "quality_score": row.ad_group_criterion.quality_info.quality_score if row.ad_group_criterion.quality_info.quality_score else None,
                    "cpc_bid_micros": row.ad_group_criterion.effective_cpc_bid_micros,
                }
                for row in response
            ]
        except Exception as e:
            logger.error("Failed to get keywords", error=str(e))
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_performance_metrics(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign.id, campaign.name,
                       segments.date,
                       metrics.impressions, metrics.clicks, metrics.cost_micros,
                       metrics.conversions, metrics.conversions_value,
                       metrics.ctr, metrics.average_cpc
                FROM campaign
                WHERE segments.date DURING {date_range}
                ORDER BY segments.date
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            return [
                {
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "date": row.segments.date,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost_micros": row.metrics.cost_micros,
                    "conversions": row.metrics.conversions,
                    "conv_value": row.metrics.conversions_value,
                    "ctr": row.metrics.ctr,
                    "avg_cpc": row.metrics.average_cpc,
                }
                for row in response
            ]
        except Exception as e:
            logger.error("Failed to get performance metrics", error=str(e))
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_conversion_actions(self) -> List[Dict[str, Any]]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = """
                SELECT conversion_action.id, conversion_action.name,
                       conversion_action.type, conversion_action.status,
                       conversion_action.category
                FROM conversion_action
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            return [
                {
                    "action_id": str(row.conversion_action.id),
                    "name": row.conversion_action.name,
                    "type": row.conversion_action.type_.name,
                    "status": row.conversion_action.status.name,
                    "category": row.conversion_action.category.name,
                }
                for row in response
            ]
        except Exception as e:
            logger.error("Failed to get conversion actions", error=str(e))
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_auction_insights(self, campaign_id: str) -> List[Dict[str, Any]]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign.id, segments.date,
                       auction_insight.display_domain,
                       metrics.auction_insight_search_impression_share,
                       metrics.auction_insight_search_overlap_rate,
                       metrics.auction_insight_search_outranking_share,
                       metrics.auction_insight_search_top_impression_percentage,
                       metrics.auction_insight_search_absolute_top_impression_percentage,
                       metrics.auction_insight_search_position_above_rate
                FROM campaign_auction_insight
                WHERE campaign.id = {campaign_id}
                  AND segments.date DURING LAST_30_DAYS
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            return [
                {
                    "date": row.segments.date,
                    "competitor_domain": row.auction_insight.display_domain,
                    "impression_share": row.metrics.auction_insight_search_impression_share,
                    "overlap_rate": row.metrics.auction_insight_search_overlap_rate,
                    "outranking_share": row.metrics.auction_insight_search_outranking_share,
                    "top_of_page_rate": row.metrics.auction_insight_search_top_impression_percentage,
                    "abs_top_rate": row.metrics.auction_insight_search_absolute_top_impression_percentage,
                    "position_above_rate": row.metrics.auction_insight_search_position_above_rate,
                }
                for row in response
            ]
        except Exception as e:
            logger.error("Failed to get auction insights", error=str(e))
            return []

    # ── WRITE OPERATIONS (CHANGESETS) ────────────────────────────────

    async def create_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_token()
        logger.info("Creating campaign", customer_id=self.customer_id, name=campaign_data.get("name"))
        try:
            client = self._get_client()
            campaign_service = client.get_service("CampaignService")
            campaign_budget_service = client.get_service("CampaignBudgetService")

            # Create budget
            budget_operation = client.get_type("CampaignBudgetOperation")
            budget = budget_operation.create
            budget.name = f"Budget - {campaign_data['name']}"
            budget.amount_micros = campaign_data.get("budget_micros", 30_000_000)
            budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

            budget_response = campaign_budget_service.mutate_campaign_budgets(
                customer_id=self.customer_id,
                operations=[budget_operation],
            )
            budget_resource = budget_response.results[0].resource_name

            # Create campaign
            campaign_operation = client.get_type("CampaignOperation")
            campaign = campaign_operation.create
            campaign.name = campaign_data["name"]
            campaign.campaign_budget = budget_resource
            campaign.status = client.enums.CampaignStatusEnum.PAUSED
            campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH

            campaign_response = campaign_service.mutate_campaigns(
                customer_id=self.customer_id,
                operations=[campaign_operation],
            )

            return {
                "campaign_resource": campaign_response.results[0].resource_name,
                "status": "created",
            }
        except Exception as e:
            logger.error("Failed to create campaign", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_ad_group(self, campaign_resource: str, ad_group_data: Dict) -> Dict[str, Any]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ag_service = client.get_service("AdGroupService")

            operation = client.get_type("AdGroupOperation")
            ag = operation.create
            ag.name = ad_group_data["name"]
            ag.campaign = campaign_resource
            ag.status = client.enums.AdGroupStatusEnum.ENABLED
            ag.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD

            response = ag_service.mutate_ad_groups(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"ad_group_resource": response.results[0].resource_name, "status": "created"}
        except Exception as e:
            logger.error("Failed to create ad group", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_keywords(self, ad_group_resource: str, keywords: List[Dict]) -> Dict[str, Any]:
        await self._ensure_token()
        try:
            client = self._get_client()
            agc_service = client.get_service("AdGroupCriterionService")

            operations = []
            for kw in keywords:
                operation = client.get_type("AdGroupCriterionOperation")
                criterion = operation.create
                criterion.ad_group = ad_group_resource
                criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                criterion.keyword.text = kw["text"]
                match_map = {
                    "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
                    "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
                    "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
                }
                criterion.keyword.match_type = match_map.get(kw.get("match_type", "PHRASE"), client.enums.KeywordMatchTypeEnum.PHRASE)
                operations.append(operation)

            response = agc_service.mutate_ad_group_criteria(
                customer_id=self.customer_id, operations=operations
            )
            return {"created": len(response.results), "status": "created"}
        except Exception as e:
            logger.error("Failed to create keywords", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_responsive_search_ad(self, ad_group_resource: str, ad_data: Dict) -> Dict[str, Any]:
        await self._ensure_token()
        try:
            client = self._get_client()
            ag_ad_service = client.get_service("AdGroupAdService")

            operation = client.get_type("AdGroupAdOperation")
            ag_ad = operation.create
            ag_ad.ad_group = ad_group_resource
            ag_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
            ag_ad.ad.final_urls.extend(ad_data.get("final_urls", []))

            for headline in ad_data.get("headlines", [])[:15]:
                h = client.get_type("AdTextAsset")
                h.text = headline[:30]
                ag_ad.ad.responsive_search_ad.headlines.append(h)

            for desc in ad_data.get("descriptions", [])[:4]:
                d = client.get_type("AdTextAsset")
                d.text = desc[:90]
                ag_ad.ad.responsive_search_ad.descriptions.append(d)

            response = ag_ad_service.mutate_ad_group_ads(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"ad_resource": response.results[0].resource_name, "status": "created"}
        except Exception as e:
            logger.error("Failed to create RSA", error=str(e))
            return {"status": "error", "error": str(e)}

    async def update_campaign_status(self, campaign_resource: str, status: str) -> Dict[str, Any]:
        await self._ensure_token()
        try:
            client = self._get_client()
            campaign_service = client.get_service("CampaignService")

            operation = client.get_type("CampaignOperation")
            campaign = operation.update
            campaign.resource_name = campaign_resource
            status_map = {
                "ENABLED": client.enums.CampaignStatusEnum.ENABLED,
                "PAUSED": client.enums.CampaignStatusEnum.PAUSED,
            }
            campaign.status = status_map.get(status, client.enums.CampaignStatusEnum.PAUSED)

            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("status")
            operation.update_mask.CopyFrom(field_mask)

            campaign_service.mutate_campaigns(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": status, "resource": campaign_resource}
        except Exception as e:
            logger.error("Failed to update campaign status", error=str(e))
            return {"status": "error", "error": str(e)}

    async def update_campaign_budget(self, budget_resource: str, new_amount_micros: int) -> Dict[str, Any]:
        await self._ensure_token()
        try:
            client = self._get_client()
            budget_service = client.get_service("CampaignBudgetService")

            operation = client.get_type("CampaignBudgetOperation")
            budget = operation.update
            budget.resource_name = budget_resource
            budget.amount_micros = new_amount_micros

            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("amount_micros")
            operation.update_mask.CopyFrom(field_mask)

            budget_service.mutate_campaign_budgets(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": "updated", "new_amount_micros": new_amount_micros}
        except Exception as e:
            logger.error("Failed to update budget", error=str(e))
            return {"status": "error", "error": str(e)}
