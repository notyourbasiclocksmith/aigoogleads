"""
Google Ads API Client — Read + Write operations with rate limiting.

Capabilities:
- Read: account structure, campaigns, ad groups, ads, assets, keywords, negatives,
  performance metrics, conversions, auction insights
- Write (via changesets): create/update campaigns, ad groups, ads, keywords, negatives,
  assets; update bids/budgets/targeting; pause/enable entities
- Atomic campaign deployment using GoogleAdsService.Mutate with temporary resource names
"""
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from google.protobuf import field_mask_pb2

from app.core.config import settings
from app.core.security import decrypt_token
from app.integrations.google_ads.oauth import refresh_access_token, OAuthTokenExpiredError

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
        self._cached_client = None

    async def _ensure_token(self):
        if self._access_token and self._token_expires_at and datetime.now(timezone.utc) < self._token_expires_at:
            return
        try:
            tokens = await refresh_access_token(self._refresh_token)
        except OAuthTokenExpiredError:
            raise  # Let this bubble up with the user-friendly message
        if tokens:
            self._access_token = tokens["access_token"]
            expires_in = tokens.get("expires_in", 3500)
            from datetime import timedelta
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 60)
        else:
            raise Exception("Failed to refresh Google Ads access token — Google returned non-200. Check client_id/secret and refresh_token.")

    def _get_client(self):
        """
        Get or create a cached Google Ads API client.
        The client is cached to reuse the gRPC channel across calls.
        """
        if self._cached_client is not None:
            return self._cached_client
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
        self._cached_client = GAdsClient.load_from_dict(credentials)
        return self._cached_client

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous Google Ads API call in a thread pool to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    @staticmethod
    def _extract_google_ads_errors(ex) -> List[Dict[str, Any]]:
        """Extract structured error details from a GoogleAdsException."""
        errors = []
        try:
            for error in ex.failure.errors:
                err = {
                    "message": error.message,
                    "error_code": str(error.error_code),
                }
                if error.location and error.location.field_path_elements:
                    err["field_path"] = ".".join(
                        str(e.field_name) for e in error.location.field_path_elements
                    )
                    # Extract operation index from field path (e.g. "operations[5]")
                    for elem in error.location.field_path_elements:
                        if elem.field_name == "mutate_operations" and elem.index is not None:
                            err["operation_index"] = elem.index
                            break
                if error.trigger and error.trigger.string_value:
                    err["trigger"] = error.trigger.string_value
                # Extract policy violation keys for exemption retry
                if hasattr(error, "details") and error.details:
                    pvd = error.details.policy_violation_details
                    if pvd and pvd.external_policy_name:
                        err["policy_name"] = pvd.external_policy_name
                        err["is_exemptible"] = pvd.is_exemptible
                        if pvd.key:
                            err["exemption_key"] = {
                                "policy_name": pvd.key.policy_name,
                                "violating_text": pvd.key.violating_text,
                            }
                    pfd = error.details.policy_finding_details
                    if pfd and pfd.policy_topic_entries:
                        topics = []
                        for entry in pfd.policy_topic_entries:
                            topics.append({
                                "topic": entry.topic,
                                "type": str(entry.type_),
                            })
                        err["policy_topics"] = topics
                errors.append(err)
        except Exception:
            errors.append({"message": str(ex)})
        return errors

    # ── READ OPERATIONS ──────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_account_info(self) -> Dict[str, Any]:
        logger.info("Fetching account info", customer_id=self.customer_id)
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
        return {"customer_id": self.customer_id, "name": ""}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_campaigns(self) -> List[Dict[str, Any]]:
        logger.info("Fetching campaigns", customer_id=self.customer_id)
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_ad_groups(self, campaign_id: str) -> List[Dict[str, Any]]:
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_keywords(self, ad_group_id: str) -> List[Dict[str, Any]]:
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_performance_metrics(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
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
        from datetime import datetime
        results = []
        for row in response:
            # Convert Google's date string to date object
            date_str = str(row.segments.date)
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            results.append({
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "date": date_obj,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conv_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "avg_cpc": row.metrics.average_cpc,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_conversion_actions(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT conversion_action.id, conversion_action.name,
                   conversion_action.type, conversion_action.status,
                   conversion_action.category,
                   conversion_action.counting_type,
                   conversion_action.attribution_model_settings.attribution_model,
                   conversion_action.attribution_model_settings.data_driven_model_status,
                   conversion_action.include_in_conversions_metric,
                   conversion_action.value_settings.default_value,
                   conversion_action.click_through_lookback_window_days,
                   conversion_action.view_through_lookback_window_days
            FROM conversion_action
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        results = []
        for row in response:
            ca = row.conversion_action
            action = {
                "action_id": str(ca.id),
                "name": ca.name,
                "type": ca.type_.name,
                "status": ca.status.name,
                "category": ca.category.name,
                "counting_type": ca.counting_type.name,
                "include_in_conversions": ca.include_in_conversions_metric,
                "click_through_lookback_days": ca.click_through_lookback_window_days,
                "view_through_lookback_days": ca.view_through_lookback_window_days,
            }
            try:
                action["attribution_model"] = ca.attribution_model_settings.attribution_model.name
                action["data_driven_model_status"] = ca.attribution_model_settings.data_driven_model_status.name
            except Exception:
                action["attribution_model"] = None
                action["data_driven_model_status"] = None
            try:
                action["default_value"] = ca.value_settings.default_value
            except Exception:
                action["default_value"] = None
            results.append(action)
        return results

    async def get_campaign_conversion_goals(self, campaign_resource: str) -> List[Dict]:
        """Get conversion goals for a specific campaign."""
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign.id,
                       campaign_conversion_goal.campaign,
                       campaign_conversion_goal.category,
                       campaign_conversion_goal.origin
                FROM campaign_conversion_goal
                WHERE campaign.resource_name = '{campaign_resource}'
            """
            response = await self._run_sync(
                ga_service.search, customer_id=self.customer_id, query=query
            )
            return [{"category": row.campaign_conversion_goal.category.name,
                      "origin": row.campaign_conversion_goal.origin.name} for row in response]
        except Exception as e:
            logger.warning("Failed to get campaign conversion goals", error=str(e))
            return []

    async def set_campaign_conversion_goals(
        self, campaign_id: str, conversion_action_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Set campaign-level conversion goals by updating CustomConversionGoal.
        For Google Ads API v17+, campaign conversion goals are managed via
        ConversionGoalCampaignConfigService or by setting conversion_actions on the campaign.

        The simplest approach: use CampaignConversionGoal to configure which
        conversion actions the campaign should optimize for.
        """
        if not conversion_action_ids:
            return {"status": "skipped", "reason": "no conversion actions provided"}

        try:
            await self._ensure_token()
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            campaign_resource = f"customers/{self.customer_id}/campaigns/{campaign_id}"

            # Update campaign to use CAMPAIGN-level conversion goal setting
            campaign_op = client.get_type("CampaignOperation")
            campaign = campaign_op.update
            campaign.resource_name = campaign_resource

            # Set conversion goal campaign config
            # This tells Google to only count the specified conversion actions
            config_service = client.get_service("CampaignConversionGoalService")

            operations = []
            for ca_id in conversion_action_ids:
                op = client.get_type("CampaignConversionGoalOperation")
                goal = op.update
                goal.campaign = campaign_resource
                goal.category = client.enums.ConversionActionCategoryEnum.DEFAULT
                goal.origin = client.enums.ConversionOriginEnum.WEBSITE

                field_mask = client.get_type("FieldMask")
                field_mask.paths.append("biddable")
                op.update_mask.CopyFrom(field_mask)
                goal.biddable = True
                operations.append(op)

            if operations:
                await self._run_sync(
                    config_service.mutate_campaign_conversion_goals,
                    customer_id=self.customer_id,
                    operations=operations,
                )

            logger.info("Campaign conversion goals set",
                campaign_id=campaign_id,
                conversion_actions=len(conversion_action_ids))
            return {"status": "success", "conversion_actions": len(conversion_action_ids)}
        except Exception as e:
            logger.warning("Failed to set campaign conversion goals",
                campaign_id=campaign_id, error=str(e))
            return {"status": "error", "error": str(e)}

    async def select_best_conversion_actions(self) -> List[Dict]:
        """
        Select the best conversion actions for a new campaign.
        Priority: LEAD > PHONE_CALL > PURCHASE > SIGNUP > OTHER
        Only returns ENABLED actions that are included_in_conversions.
        """
        try:
            all_actions = await self.get_conversion_actions()

            # Filter to enabled, included-in-conversions actions
            active = [
                a for a in all_actions
                if a.get("status") == "ENABLED"
                and a.get("include_in_conversions", False)
            ]

            if not active:
                # Fall back to any enabled action
                active = [a for a in all_actions if a.get("status") == "ENABLED"]

            # Priority ordering
            priority = {"LEAD": 1, "PHONE_CALL_LEAD": 2, "PHONE_CALL": 3,
                        "SUBMIT_LEAD_FORM": 4, "PURCHASE": 5, "SIGNUP": 6,
                        "BOOK_APPOINTMENT": 7, "REQUEST_QUOTE": 8,
                        "GET_DIRECTIONS": 9, "CONTACT": 10, "DEFAULT": 99}

            active.sort(key=lambda a: priority.get(a.get("category", "DEFAULT"), 50))

            # Return top 3 most relevant
            return active[:3]
        except Exception as e:
            logger.warning("Failed to select conversion actions", error=str(e))
            return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_auction_insights(self, campaign_id: str) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign.id, segments.date,
                       auction_insight.domain,
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
                    "competitor_domain": row.auction_insight.domain,
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_ads(self, ad_group_id: str) -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT ad_group_ad.ad.id, ad_group_ad.ad.type,
                   ad_group_ad.ad.responsive_search_ad.headlines,
                   ad_group_ad.ad.responsive_search_ad.descriptions,
                   ad_group_ad.ad.final_urls,
                   ad_group_ad.status
            FROM ad_group_ad
            WHERE ad_group.id = {ad_group_id}
              AND ad_group_ad.status != 'REMOVED'
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        ads = []
        for row in response:
            ad = row.ad_group_ad.ad
            headlines = []
            descriptions = []
            try:
                headlines = [h.text for h in ad.responsive_search_ad.headlines]
                descriptions = [d.text for d in ad.responsive_search_ad.descriptions]
            except Exception:
                pass
            ads.append({
                "ad_id": str(ad.id),
                "type": ad.type_.name if hasattr(ad.type_, 'name') else str(ad.type_),
                "headlines": headlines,
                "descriptions": descriptions,
                "final_urls": list(ad.final_urls),
                "status": row.ad_group_ad.status.name,
            })
        return ads

    # ── NEW DATA PIPELINES ─────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_search_terms(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT search_term_view.search_term,
                   campaign.id, ad_group.id,
                   segments.keyword.info.text,
                   segments.keyword.ad_group_criterion,
                   segments.date,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc
            FROM search_term_view
            WHERE segments.date DURING {date_range}
            ORDER BY metrics.cost_micros DESC
            LIMIT 5000
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        from datetime import datetime as dt
        results = []
        for row in response:
            date_str = str(row.segments.date)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()
            keyword_text = ""
            keyword_id = ""
            try:
                keyword_text = row.segments.keyword.info.text
                criterion_rn = row.segments.keyword.ad_group_criterion
                keyword_id = criterion_rn.split("~")[-1] if criterion_rn else ""
            except Exception:
                pass
            results.append({
                "search_term": row.search_term_view.search_term,
                "campaign_id": str(row.campaign.id),
                "ad_group_id": str(row.ad_group.id),
                "keyword_id": keyword_id,
                "keyword_text": keyword_text,
                "date": date_obj,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conversion_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "average_cpc_micros": row.metrics.average_cpc,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_keyword_performance(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT ad_group_criterion.criterion_id,
                   ad_group_criterion.keyword.text,
                   ad_group_criterion.keyword.match_type,
                   ad_group_criterion.quality_info.quality_score,
                   campaign.id, ad_group.id, segments.date,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc
            FROM keyword_view
            WHERE segments.date DURING {date_range}
              AND ad_group_criterion.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        from datetime import datetime as dt
        results = []
        for row in response:
            date_str = str(row.segments.date)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()
            qs = row.ad_group_criterion.quality_info.quality_score
            results.append({
                "keyword_id": str(row.ad_group_criterion.criterion_id),
                "keyword_text": row.ad_group_criterion.keyword.text,
                "match_type": row.ad_group_criterion.keyword.match_type.name,
                "campaign_id": str(row.campaign.id),
                "ad_group_id": str(row.ad_group.id),
                "date": date_obj,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conversion_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "average_cpc_micros": row.metrics.average_cpc,
                "quality_score": qs if qs else None,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_ad_performance(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT ad_group_ad.ad.id, campaign.id, ad_group.id,
                   segments.date,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc
            FROM ad_group_ad
            WHERE segments.date DURING {date_range}
              AND ad_group_ad.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        from datetime import datetime as dt
        results = []
        for row in response:
            date_str = str(row.segments.date)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()
            results.append({
                "ad_id": str(row.ad_group_ad.ad.id),
                "campaign_id": str(row.campaign.id),
                "ad_group_id": str(row.ad_group.id),
                "date": date_obj,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conversion_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "average_cpc_micros": row.metrics.average_cpc,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_ad_group_performance(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT ad_group.id, campaign.id, segments.date,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc
            FROM ad_group
            WHERE segments.date DURING {date_range}
              AND ad_group.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        from datetime import datetime as dt
        results = []
        for row in response:
            date_str = str(row.segments.date)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()
            results.append({
                "ad_group_id": str(row.ad_group.id),
                "campaign_id": str(row.campaign.id),
                "date": date_obj,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conversion_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "average_cpc_micros": row.metrics.average_cpc,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    # ── SEGMENTED PERFORMANCE QUERIES ──────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_device_performance(
        self, date_range: str = "LAST_30_DAYS", campaign_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Performance breakdown by device (MOBILE, DESKTOP, TABLET)."""
        await self._ensure_token()
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""
        query = f"""
            SELECT segments.device,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc
            FROM campaign
            WHERE segments.date DURING {date_range}
            {campaign_filter}
        """
        response = await self._run_sync(
            ga_service.search, customer_id=self.customer_id, query=query
        )
        results = []
        for row in response:
            results.append({
                "device": row.segments.device.name,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conv_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "avg_cpc": row.metrics.average_cpc,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_hour_of_day_performance(
        self, date_range: str = "LAST_30_DAYS", campaign_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Performance breakdown by hour of day (0-23)."""
        await self._ensure_token()
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""
        query = f"""
            SELECT segments.hour,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE segments.date DURING {date_range}
            {campaign_filter}
        """
        response = await self._run_sync(
            ga_service.search, customer_id=self.customer_id, query=query
        )
        results = []
        for row in response:
            results.append({
                "hour": row.segments.hour,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conv_value": row.metrics.conversions_value,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_day_of_week_performance(
        self, date_range: str = "LAST_30_DAYS", campaign_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Performance breakdown by day of week."""
        await self._ensure_token()
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""
        query = f"""
            SELECT segments.day_of_week,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE segments.date DURING {date_range}
            {campaign_filter}
        """
        response = await self._run_sync(
            ga_service.search, customer_id=self.customer_id, query=query
        )
        results = []
        for row in response:
            results.append({
                "day_of_week": row.segments.day_of_week.name,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conv_value": row.metrics.conversions_value,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_geo_performance(
        self, date_range: str = "LAST_30_DAYS", campaign_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Performance breakdown by geographic location (city/metro)."""
        await self._ensure_token()
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        campaign_filter = f"AND campaign.id = {campaign_id}" if campaign_id else ""
        query = f"""
            SELECT geographic_view.country_criterion_id,
                   geographic_view.location_type,
                   segments.geo_target_city,
                   segments.geo_target_metro,
                   segments.geo_target_region,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value
            FROM geographic_view
            WHERE segments.date DURING {date_range}
            {campaign_filter}
            ORDER BY metrics.clicks DESC
            LIMIT 100
        """
        response = await self._run_sync(
            ga_service.search, customer_id=self.customer_id, query=query
        )
        results = []
        for row in response:
            city_id = ""
            metro_id = ""
            region_id = ""
            try:
                city_id = str(row.segments.geo_target_city)
            except Exception:
                pass
            try:
                metro_id = str(row.segments.geo_target_metro)
            except Exception:
                pass
            try:
                region_id = str(row.segments.geo_target_region)
            except Exception:
                pass
            results.append({
                "city_criterion_id": city_id,
                "metro_criterion_id": metro_id,
                "region_criterion_id": region_id,
                "location_type": row.geographic_view.location_type.name if hasattr(row.geographic_view, 'location_type') else "",
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conv_value": row.metrics.conversions_value,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_campaign_performance_detail(
        self, campaign_id: str, date_range: str = "LAST_30_DAYS"
    ) -> Dict[str, Any]:
        """Comprehensive campaign-specific performance with daily trends."""
        await self._ensure_token()
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")

        # Daily trends
        query = f"""
            SELECT segments.date,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.ctr, metrics.average_cpc,
                   metrics.search_impression_share,
                   metrics.search_top_impression_share,
                   metrics.search_absolute_top_impression_share
            FROM campaign
            WHERE campaign.id = {campaign_id}
            AND segments.date DURING {date_range}
            ORDER BY segments.date
        """
        response = await self._run_sync(
            ga_service.search, customer_id=self.customer_id, query=query
        )
        from datetime import datetime as dt
        trends = []
        totals = {
            "impressions": 0, "clicks": 0, "cost_micros": 0,
            "conversions": 0.0, "conv_value": 0.0,
        }
        for row in response:
            date_str = str(row.segments.date)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()

            imp_share = None
            top_share = None
            abs_top_share = None
            try:
                imp_share = row.metrics.search_impression_share
            except Exception:
                pass
            try:
                top_share = row.metrics.search_top_impression_share
            except Exception:
                pass
            try:
                abs_top_share = row.metrics.search_absolute_top_impression_share
            except Exception:
                pass

            day = {
                "date": str(date_obj),
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "cost": row.metrics.cost_micros / 1_000_000,
                "conversions": row.metrics.conversions,
                "conv_value": row.metrics.conversions_value,
                "ctr": row.metrics.ctr,
                "avg_cpc": row.metrics.average_cpc,
                "impression_share": imp_share,
                "top_impression_share": top_share,
                "abs_top_impression_share": abs_top_share,
            }
            trends.append(day)
            totals["impressions"] += row.metrics.impressions
            totals["clicks"] += row.metrics.clicks
            totals["cost_micros"] += row.metrics.cost_micros
            totals["conversions"] += row.metrics.conversions
            totals["conv_value"] += row.metrics.conversions_value

        cost = totals["cost_micros"] / 1_000_000
        return {
            "campaign_id": campaign_id,
            "trends": trends,
            "totals": {
                **totals,
                "cost": cost,
                "ctr": totals["clicks"] / totals["impressions"] if totals["impressions"] > 0 else 0,
                "cpc": cost / totals["clicks"] if totals["clicks"] > 0 else 0,
                "cpa": cost / totals["conversions"] if totals["conversions"] > 0 else 0,
                "roas": totals["conv_value"] / cost if cost > 0 else 0,
            },
        }

    async def get_landing_page_performance(self, date_range: str = "LAST_30_DAYS") -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT landing_page_view.unexpanded_final_url,
                   campaign.id, ad_group.id, segments.date,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value,
                   metrics.mobile_friendly_clicks_percentage,
                   metrics.speed_score
            FROM landing_page_view
            WHERE segments.date DURING {date_range}
            ORDER BY metrics.clicks DESC
            LIMIT 2000
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        from datetime import datetime as dt
        results = []
        for row in response:
            date_str = str(row.segments.date)
            date_obj = dt.strptime(date_str, "%Y-%m-%d").date()
            mobile_rate = None
            speed = None
            try:
                mobile_rate = row.metrics.mobile_friendly_clicks_percentage
            except Exception:
                pass
            try:
                speed = row.metrics.speed_score
            except Exception:
                pass
            results.append({
                "landing_page_url": row.landing_page_view.unexpanded_final_url,
                "campaign_id": str(row.campaign.id),
                "ad_group_id": str(row.ad_group.id),
                "date": date_obj,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost_micros": row.metrics.cost_micros,
                "conversions": row.metrics.conversions,
                "conversion_value": row.metrics.conversions_value,
                "mobile_friendly_click_rate": mobile_rate,
                "speed_score": speed,
            })
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_google_recommendations(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = """
            SELECT recommendation.resource_name,
                   recommendation.type,
                   recommendation.impact,
                   recommendation.campaign,
                   recommendation.ad_group,
                   recommendation.campaign_budget_recommendation,
                   recommendation.keyword_recommendation,
                   recommendation.text_ad_recommendation,
                   recommendation.sitelink_asset_recommendation,
                   recommendation.responsive_search_ad_recommendation
            FROM recommendation
        """
        response = ga_service.search(customer_id=self.customer_id, query=query)
        results = []
        for row in response:
            rec = row.recommendation
            campaign_id = ""
            ad_group_id = ""
            try:
                if rec.campaign:
                    campaign_id = rec.campaign.split("/")[-1]
            except Exception:
                pass
            try:
                if rec.ad_group:
                    ad_group_id = rec.ad_group.split("/")[-1]
            except Exception:
                pass

            impact_base = {}
            impact_potential = {}
            try:
                impact = rec.impact
                if impact and impact.base_metrics:
                    bm = impact.base_metrics
                    impact_base = {
                        "impressions": getattr(bm, "impressions", None),
                        "clicks": getattr(bm, "clicks", None),
                        "cost_micros": getattr(bm, "cost_micros", None),
                        "conversions": getattr(bm, "conversions", None),
                    }
                if impact and impact.potential_metrics:
                    pm = impact.potential_metrics
                    impact_potential = {
                        "impressions": getattr(pm, "impressions", None),
                        "clicks": getattr(pm, "clicks", None),
                        "cost_micros": getattr(pm, "cost_micros", None),
                        "conversions": getattr(pm, "conversions", None),
                    }
            except Exception:
                pass

            details = {}
            rec_type_name = rec.type_.name if hasattr(rec.type_, 'name') else str(rec.type_)
            try:
                if rec_type_name == "KEYWORD" and rec.keyword_recommendation:
                    kr = rec.keyword_recommendation
                    details = {
                        "keyword": kr.keyword.text if kr.keyword else "",
                        "match_type": kr.keyword.match_type.name if kr.keyword else "",
                        "recommended_cpc_bid_micros": kr.recommended_cpc_bid_micros if hasattr(kr, 'recommended_cpc_bid_micros') else None,
                    }
                elif rec_type_name == "CAMPAIGN_BUDGET" and rec.campaign_budget_recommendation:
                    cbr = rec.campaign_budget_recommendation
                    details = {
                        "current_budget_micros": cbr.current_budget_amount_micros if hasattr(cbr, 'current_budget_amount_micros') else None,
                        "recommended_budget_micros": cbr.recommended_budget_amount_micros if hasattr(cbr, 'recommended_budget_amount_micros') else None,
                    }
                elif rec_type_name == "RESPONSIVE_SEARCH_AD" and rec.responsive_search_ad_recommendation:
                    rsar = rec.responsive_search_ad_recommendation
                    details = {"ad": str(rsar)}
            except Exception:
                pass

            results.append({
                "resource_name": rec.resource_name,
                "type": rec_type_name,
                "campaign_id": campaign_id,
                "ad_group_id": ad_group_id,
                "impact_base": impact_base,
                "impact_potential": impact_potential,
                "details": details,
            })
        return results

    async def apply_google_recommendation(self, resource_name: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            rec_service = client.get_service("RecommendationService")
            operation = client.get_type("ApplyRecommendationOperation")
            operation.resource_name = resource_name
            response = rec_service.apply_recommendation(
                customer_id=self.customer_id,
                operations=[operation],
            )
            return {"status": "applied", "resource": resource_name}
        except Exception as e:
            logger.error("Failed to apply recommendation", error=str(e))
            return {"status": "error", "error": str(e)}

    async def dismiss_google_recommendation(self, resource_name: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            rec_service = client.get_service("RecommendationService")
            operation = client.get_type("DismissRecommendationRequest.DismissRecommendationOperation")
            operation.resource_name = resource_name
            response = rec_service.dismiss_recommendation(
                customer_id=self.customer_id,
                operations=[operation],
            )
            return {"status": "dismissed", "resource": resource_name}
        except Exception as e:
            logger.error("Failed to dismiss recommendation", error=str(e))
            return {"status": "error", "error": str(e)}

    async def get_keyword_ideas(self, seed_keywords: List[str], location_id: str = "2840",
                                 language_id: str = "1000") -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            kp_service = client.get_service("KeywordPlanIdeaService")

            request = client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = self.customer_id
            request.language = f"languageConstants/{language_id}"
            request.geo_target_constants.append(f"geoTargetConstants/{location_id}")
            request.keyword_plan_network = client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH

            seed = request.keyword_seed
            for kw in seed_keywords:
                seed.keywords.append(kw)

            response = kp_service.generate_keyword_ideas(request=request)
            results = []
            for idea in response:
                avg_monthly = 0
                competition = "UNKNOWN"
                low_bid = 0
                high_bid = 0
                try:
                    km = idea.keyword_idea_metrics
                    avg_monthly = km.avg_monthly_searches
                    competition = km.competition.name if hasattr(km.competition, 'name') else str(km.competition)
                    low_bid = km.low_top_of_page_bid_micros
                    high_bid = km.high_top_of_page_bid_micros
                except Exception:
                    pass
                results.append({
                    "keyword": idea.text,
                    "avg_monthly_searches": avg_monthly,
                    "competition": competition,
                    "low_top_of_page_bid_micros": low_bid,
                    "high_top_of_page_bid_micros": high_bid,
                })
            return results
        except Exception as e:
            logger.error("Failed to get keyword ideas", error=str(e))
            return []

    # ── MUTATION OPERATIONS ──────────────────────────────────────────

    async def add_negative_keywords(self, campaign_id: str, keywords: List[str]) -> Dict[str, Any]:
        try:
            client = self._get_client()
            campaign_criterion_service = client.get_service("CampaignCriterionService")
            campaign_resource = f"customers/{self.customer_id}/campaigns/{campaign_id}"

            operations = []
            for kw_text in keywords:
                operation = client.get_type("CampaignCriterionOperation")
                criterion = operation.create
                criterion.campaign = campaign_resource
                criterion.negative = True
                criterion.keyword.text = kw_text
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
                operations.append(operation)

            response = campaign_criterion_service.mutate_campaign_criteria(
                customer_id=self.customer_id,
                operations=operations,
                partial_failure=True,
            )
            failed = 0
            if response.partial_failure_error:
                from google.ads.googleads.v23.errors.types.errors import GoogleAdsFailure
                failure = GoogleAdsFailure()
                failure._pb.MergeFrom(response.partial_failure_error)
                for error in failure.errors:
                    logger.warning("Negative keyword partial failure",
                        message=error.message)
                    failed += 1
            return {"status": "created", "count": len(response.results) - failed, "failed": failed}
        except Exception as e:
            logger.error("Failed to add negative keywords", error=str(e))
            return {"status": "error", "error": str(e)}

    async def update_keyword_bid(self, ad_group_id: str, criterion_id: str,
                                  new_cpc_bid_micros: int) -> Dict[str, Any]:
        try:
            client = self._get_client()
            agc_service = client.get_service("AdGroupCriterionService")

            resource_name = f"customers/{self.customer_id}/adGroupCriteria/{ad_group_id}~{criterion_id}"
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.update
            criterion.resource_name = resource_name
            criterion.cpc_bid_micros = new_cpc_bid_micros

            field_mask = field_mask_pb2.FieldMask(paths=["cpc_bid_micros"])
            operation.update_mask.CopyFrom(field_mask)

            agc_service.mutate_ad_group_criteria(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": "updated", "criterion_id": criterion_id, "new_cpc_bid_micros": new_cpc_bid_micros}
        except Exception as e:
            logger.error("Failed to update keyword bid", error=str(e))
            return {"status": "error", "error": str(e)}

    async def update_keyword_status(self, ad_group_id: str, criterion_id: str,
                                     status: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            agc_service = client.get_service("AdGroupCriterionService")

            resource_name = f"customers/{self.customer_id}/adGroupCriteria/{ad_group_id}~{criterion_id}"
            operation = client.get_type("AdGroupCriterionOperation")
            criterion = operation.update
            criterion.resource_name = resource_name
            status_map = {
                "ENABLED": client.enums.AdGroupCriterionStatusEnum.ENABLED,
                "PAUSED": client.enums.AdGroupCriterionStatusEnum.PAUSED,
            }
            criterion.status = status_map.get(status, client.enums.AdGroupCriterionStatusEnum.PAUSED)

            field_mask = field_mask_pb2.FieldMask(paths=["status"])
            operation.update_mask.CopyFrom(field_mask)

            agc_service.mutate_ad_group_criteria(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": status, "criterion_id": criterion_id}
        except Exception as e:
            logger.error("Failed to update keyword status", error=str(e))
            return {"status": "error", "error": str(e)}

    async def update_ad_status(self, ad_group_id: str, ad_id: str, status: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            ag_ad_service = client.get_service("AdGroupAdService")

            resource_name = f"customers/{self.customer_id}/adGroupAds/{ad_group_id}~{ad_id}"
            operation = client.get_type("AdGroupAdOperation")
            ag_ad = operation.update
            ag_ad.resource_name = resource_name
            status_map = {
                "ENABLED": client.enums.AdGroupAdStatusEnum.ENABLED,
                "PAUSED": client.enums.AdGroupAdStatusEnum.PAUSED,
            }
            ag_ad.status = status_map.get(status, client.enums.AdGroupAdStatusEnum.PAUSED)

            field_mask = field_mask_pb2.FieldMask(paths=["status"])
            operation.update_mask.CopyFrom(field_mask)

            ag_ad_service.mutate_ad_group_ads(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": status, "ad_id": ad_id}
        except Exception as e:
            logger.error("Failed to update ad status", error=str(e))
            return {"status": "error", "error": str(e)}

    async def update_ad_group_status(self, ad_group_id: str, status: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            ag_service = client.get_service("AdGroupService")

            resource_name = f"customers/{self.customer_id}/adGroups/{ad_group_id}"
            operation = client.get_type("AdGroupOperation")
            ag = operation.update
            ag.resource_name = resource_name
            status_map = {
                "ENABLED": client.enums.AdGroupStatusEnum.ENABLED,
                "PAUSED": client.enums.AdGroupStatusEnum.PAUSED,
            }
            ag.status = status_map.get(status, client.enums.AdGroupStatusEnum.PAUSED)

            field_mask = field_mask_pb2.FieldMask(paths=["status"])
            operation.update_mask.CopyFrom(field_mask)

            ag_service.mutate_ad_groups(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": status, "ad_group_id": ad_group_id}
        except Exception as e:
            logger.error("Failed to update ad group status", error=str(e))
            return {"status": "error", "error": str(e)}

    async def set_device_bid_modifier(self, campaign_id: str, device: str,
                                       bid_modifier: float) -> Dict[str, Any]:
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            campaign_criterion_service = client.get_service("CampaignCriterionService")

            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = ga_service.campaign_path(self.customer_id, campaign_id)
            criterion.device.type_ = client.enums.DeviceEnum[device.upper()]
            criterion.bid_modifier = bid_modifier

            await self._run_sync(
                campaign_criterion_service.mutate_campaign_criteria,
                customer_id=self.customer_id, operations=[operation],
            )
            return {"status": "set", "device": device, "bid_modifier": bid_modifier}
        except Exception as e:
            logger.error("Failed to set device bid modifier", error=str(e))
            return {"status": "error", "error": str(e)}

    async def add_location_targeting(self, campaign_id: str, location_id: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            campaign_criterion_service = client.get_service("CampaignCriterionService")

            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
            criterion.location.geo_target_constant = f"geoTargetConstants/{location_id}"

            await self._run_sync(
                campaign_criterion_service.mutate_campaign_criteria,
                customer_id=self.customer_id, operations=[operation],
            )
            return {"status": "added", "location_id": location_id}
        except Exception as e:
            logger.error("Failed to add location targeting", error=str(e))
            return {"status": "error", "error": str(e)}

    async def add_proximity_targeting(self, campaign_id: str, latitude: float, longitude: float,
                                       radius_miles: float) -> Dict[str, Any]:
        try:
            client = self._get_client()
            campaign_criterion_service = client.get_service("CampaignCriterionService")

            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
            criterion.proximity.address.city_name = ""
            criterion.proximity.geo_point.latitude_in_micro_degrees = int(latitude * 1_000_000)
            criterion.proximity.geo_point.longitude_in_micro_degrees = int(longitude * 1_000_000)
            criterion.proximity.radius = radius_miles
            criterion.proximity.radius_units = client.enums.ProximityRadiusUnitsEnum.MILES

            await self._run_sync(
                campaign_criterion_service.mutate_campaign_criteria,
                customer_id=self.customer_id, operations=[operation],
            )
            return {"status": "added", "latitude": latitude, "longitude": longitude, "radius_miles": radius_miles}
        except Exception as e:
            logger.error("Failed to add proximity targeting", error=str(e))
            return {"status": "error", "error": str(e)}

    async def set_ad_schedule(self, campaign_id: str, day_of_week: str,
                               start_hour: int, end_hour: int,
                               bid_modifier: float = 1.0) -> Dict[str, Any]:
        try:
            client = self._get_client()
            campaign_criterion_service = client.get_service("CampaignCriterionService")

            operation = client.get_type("CampaignCriterionOperation")
            criterion = operation.create
            criterion.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"

            day_map = {
                "MONDAY": client.enums.DayOfWeekEnum.MONDAY,
                "TUESDAY": client.enums.DayOfWeekEnum.TUESDAY,
                "WEDNESDAY": client.enums.DayOfWeekEnum.WEDNESDAY,
                "THURSDAY": client.enums.DayOfWeekEnum.THURSDAY,
                "FRIDAY": client.enums.DayOfWeekEnum.FRIDAY,
                "SATURDAY": client.enums.DayOfWeekEnum.SATURDAY,
                "SUNDAY": client.enums.DayOfWeekEnum.SUNDAY,
            }
            criterion.ad_schedule.day_of_week = day_map.get(day_of_week.upper(), client.enums.DayOfWeekEnum.MONDAY)
            criterion.ad_schedule.start_hour = start_hour
            criterion.ad_schedule.start_minute = client.enums.MinuteOfHourEnum.ZERO
            criterion.ad_schedule.end_hour = end_hour
            criterion.ad_schedule.end_minute = client.enums.MinuteOfHourEnum.ZERO
            criterion.bid_modifier = bid_modifier

            await self._run_sync(
                campaign_criterion_service.mutate_campaign_criteria,
                customer_id=self.customer_id, operations=[operation],
            )
            return {"status": "set", "day": day_of_week, "start": start_hour, "end": end_hour}
        except Exception as e:
            logger.error("Failed to set ad schedule", error=str(e))
            return {"status": "error", "error": str(e)}

    async def upload_offline_conversions(self, conversions: List[Dict[str, Any]],
                                          conversion_action_id: str) -> Dict[str, Any]:
        try:
            client = self._get_client()
            conversion_upload_service = client.get_service("ConversionUploadService")

            operations = []
            for conv in conversions:
                click_conversion = client.get_type("ClickConversion")
                click_conversion.gclid = conv["gclid"]
                click_conversion.conversion_action = f"customers/{self.customer_id}/conversionActions/{conversion_action_id}"
                click_conversion.conversion_date_time = conv["conversion_time"]
                click_conversion.conversion_value = conv.get("conversion_value", 0)
                click_conversion.currency_code = conv.get("currency", "USD")
                operations.append(click_conversion)

            request = client.get_type("UploadClickConversionsRequest")
            request.customer_id = self.customer_id
            request.conversions.extend(operations)
            request.partial_failure = True

            response = conversion_upload_service.upload_click_conversions(request=request)
            success_count = sum(1 for r in response.results if r.gclid)
            return {"status": "uploaded", "total": len(conversions), "success": success_count}
        except Exception as e:
            logger.error("Failed to upload offline conversions", error=str(e))
            return {"status": "error", "error": str(e)}

    async def list_accessible_customers(self) -> List[Dict[str, Any]]:
        try:
            client = self._get_client()
            customer_service = client.get_service("CustomerService")
            ga_service = client.get_service("GoogleAdsService")
            accessible = customer_service.list_accessible_customers()

            accounts = []
            for resource_name in accessible.resource_names:
                cid = resource_name.split("/")[-1]
                try:
                    query = """
                        SELECT customer.id, customer.descriptive_name,
                               customer.currency_code, customer.time_zone,
                               customer.manager, customer.status
                        FROM customer
                        LIMIT 1
                    """
                    for row in ga_service.search(customer_id=cid, query=query):
                        accounts.append({
                            "customer_id": str(row.customer.id),
                            "descriptive_name": row.customer.descriptive_name,
                            "currency": row.customer.currency_code,
                            "timezone": row.customer.time_zone,
                            "is_manager": row.customer.manager,
                            "status": row.customer.status.name if hasattr(row.customer.status, 'name') else str(row.customer.status),
                        })
                except Exception:
                    accounts.append({"customer_id": cid, "descriptive_name": f"Account {cid}", "error": True})
            return accounts
        except Exception as e:
            logger.error("Failed to list accessible customers", error=str(e))
            return []

    # ── WRITE OPERATIONS (CHANGESETS) ────────────────────────────────

    async def create_campaign(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a full campaign with budget, bidding strategy, and network settings.

        campaign_data keys:
          - name (str, required)
          - budget_micros (int, default 30M = $30/day)
          - bidding_strategy (str): MAXIMIZE_CONVERSIONS | TARGET_CPA | MAXIMIZE_CONVERSION_VALUE | MAXIMIZE_CLICKS
          - target_cpa_micros (int, optional): for TARGET_CPA strategy
          - channel_type (str): SEARCH | PERFORMANCE_MAX | DISPLAY (default SEARCH)
          - network (str): SEARCH | ALL (default SEARCH)
        """
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
            budget.explicitly_shared = False

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
            # Required in Google Ads API v23+ (enum, not boolean: 3 = DOES_NOT_CONTAIN)
            campaign.contains_eu_political_advertising = (
                client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
            )

            # Channel type
            channel = campaign_data.get("channel_type", "SEARCH").upper()
            channel_map = {
                "SEARCH": client.enums.AdvertisingChannelTypeEnum.SEARCH,
                "DISPLAY": client.enums.AdvertisingChannelTypeEnum.DISPLAY,
                "PERFORMANCE_MAX": client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX,
                "CALL": client.enums.AdvertisingChannelTypeEnum.SEARCH,
            }
            campaign.advertising_channel_type = channel_map.get(
                channel, client.enums.AdvertisingChannelTypeEnum.SEARCH
            )

            # Geo target type: PRESENCE = only people physically in the area
            # (NOT PRESENCE_OR_INTEREST which wastes budget on people just "interested in" the location)
            campaign.geo_target_type_setting.positive_geo_target_type = (
                client.enums.PositiveGeoTargetTypeEnum.PRESENCE
            )
            campaign.geo_target_type_setting.negative_geo_target_type = (
                client.enums.NegativeGeoTargetTypeEnum.PRESENCE
            )

            # Network settings (Search campaigns only)
            if channel in ("SEARCH", "CALL"):
                network = campaign_data.get("network", "SEARCH").upper()
                campaign.network_settings.target_google_search = True
                campaign.network_settings.target_search_network = (network == "ALL")
                campaign.network_settings.target_content_network = False

            # Bidding strategy
            bid_strategy = campaign_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS").upper()
            if bid_strategy == "MAXIMIZE_CONVERSIONS":
                campaign.maximize_conversions.target_cpa_micros = campaign_data.get("target_cpa_micros", 0)
            elif bid_strategy == "TARGET_CPA":
                campaign.maximize_conversions.target_cpa_micros = campaign_data.get("target_cpa_micros", 25_000_000)
            elif bid_strategy == "MAXIMIZE_CONVERSION_VALUE":
                campaign.maximize_conversion_value.target_roas = campaign_data.get("target_roas", 0)
            elif bid_strategy == "MAXIMIZE_CLICKS":
                campaign.maximize_clicks.cpc_bid_ceiling_micros = campaign_data.get("cpc_ceiling_micros", 0)

            campaign_response = campaign_service.mutate_campaigns(
                customer_id=self.customer_id,
                operations=[campaign_operation],
            )

            campaign_resource = campaign_response.results[0].resource_name
            # Extract numeric campaign ID from resource: customers/123/campaigns/456
            campaign_id = campaign_resource.split("/")[-1]

            return {
                "campaign_resource": campaign_resource,
                "campaign_id": campaign_id,
                "budget_resource": budget_resource,
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
            # Support both Search and Display ad group types
            ag_type = ad_group_data.get("type", "SEARCH_STANDARD").upper()
            type_map = {
                "SEARCH_STANDARD": client.enums.AdGroupTypeEnum.SEARCH_STANDARD,
                "DISPLAY_STANDARD": client.enums.AdGroupTypeEnum.DISPLAY_STANDARD,
            }
            ag.type_ = type_map.get(ag_type, client.enums.AdGroupTypeEnum.SEARCH_STANDARD)

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
                customer_id=self.customer_id,
                operations=operations,
                partial_failure=True,
            )
            # Check for partial failures
            failed = 0
            if response.partial_failure_error:
                from google.ads.googleads.v23.errors.types.errors import GoogleAdsFailure
                failure = GoogleAdsFailure()
                failure._pb.MergeFrom(response.partial_failure_error)
                for error in failure.errors:
                    logger.warning("Keyword creation partial failure",
                        message=error.message,
                        trigger=getattr(error.trigger, 'string_value', ''))
                    failed += 1
            created = len(response.results) - failed
            return {"created": created, "failed": failed, "status": "created"}
        except Exception as e:
            logger.error("Failed to create keywords", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_responsive_search_ad(self, ad_group_resource: str, ad_data: Dict) -> Dict[str, Any]:
        """Create a Responsive Search Ad (RSA). Requires at least 3 headlines and 2 descriptions."""
        headlines = ad_data.get("headlines", [])
        descriptions = ad_data.get("descriptions", [])

        # Validate minimum requirements (Google Ads requires 3+ headlines, 2+ descriptions)
        if len(headlines) < 3:
            logger.error("RSA needs at least 3 headlines", got=len(headlines))
            return {"status": "error", "error": f"RSA requires at least 3 headlines, got {len(headlines)}"}
        if len(descriptions) < 2:
            logger.error("RSA needs at least 2 descriptions", got=len(descriptions))
            return {"status": "error", "error": f"RSA requires at least 2 descriptions, got {len(descriptions)}"}

        await self._ensure_token()
        try:
            client = self._get_client()
            ag_ad_service = client.get_service("AdGroupAdService")

            operation = client.get_type("AdGroupAdOperation")
            ag_ad = operation.create
            ag_ad.ad_group = ad_group_resource
            ag_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
            # Accept both "final_urls" (list) and "final_url" (string)
            final_urls = ad_data.get("final_urls") or []
            if not final_urls and ad_data.get("final_url"):
                final_urls = [ad_data["final_url"]]
            if not final_urls:
                # Fallback: use business website from account or a placeholder
                final_urls = ["https://www.nyblocksmith.com"]
            ag_ad.ad.final_urls.extend(final_urls)

            # Display path (path1/path2) — shown in the ad URL, e.g. example.com/Locksmith/DFW
            display_path = ad_data.get("display_path", [])
            if display_path and len(display_path) >= 1:
                ag_ad.ad.responsive_search_ad.path1 = str(display_path[0])[:15]
            if display_path and len(display_path) >= 2:
                ag_ad.ad.responsive_search_ad.path2 = str(display_path[1])[:15]

            # Pinning position map (for forcing specific headlines/descriptions into certain slots)
            pin_map = {
                "HEADLINE_1": client.enums.ServedAssetFieldTypeEnum.HEADLINE_1,
                "HEADLINE_2": client.enums.ServedAssetFieldTypeEnum.HEADLINE_2,
                "HEADLINE_3": client.enums.ServedAssetFieldTypeEnum.HEADLINE_3,
                "DESCRIPTION_1": client.enums.ServedAssetFieldTypeEnum.DESCRIPTION_1,
                "DESCRIPTION_2": client.enums.ServedAssetFieldTypeEnum.DESCRIPTION_2,
            }

            for headline in headlines[:15]:
                text = headline if isinstance(headline, str) else headline.get("text", "") if isinstance(headline, dict) else str(headline)
                if not text.strip():
                    continue
                h = client.get_type("AdTextAsset")
                h.text = text.strip()[:30]
                # Support pinning: {"text": "Call Now", "pinned_position": "HEADLINE_1"}
                if isinstance(headline, dict) and headline.get("pinned_position"):
                    pin_enum = pin_map.get(headline["pinned_position"].upper())
                    if pin_enum:
                        h.pinned_field = pin_enum
                ag_ad.ad.responsive_search_ad.headlines.append(h)

            for desc in descriptions[:4]:
                text = desc if isinstance(desc, str) else desc.get("text", "") if isinstance(desc, dict) else str(desc)
                if not text.strip():
                    continue
                d = client.get_type("AdTextAsset")
                d.text = text.strip()[:90]
                if isinstance(desc, dict) and desc.get("pinned_position"):
                    pin_enum = pin_map.get(desc["pinned_position"].upper())
                    if pin_enum:
                        d.pinned_field = pin_enum
                ag_ad.ad.responsive_search_ad.descriptions.append(d)

            response = ag_ad_service.mutate_ad_group_ads(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"ad_resource": response.results[0].resource_name, "status": "created"}
        except Exception as e:
            logger.error("Failed to create RSA", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_call_ad(self, ad_group_resource: str, ad_data: Dict) -> Dict[str, Any]:
        """Create a Call-Only ad — phone number shows directly, user taps to call."""
        await self._ensure_token()
        try:
            client = self._get_client()
            ag_ad_service = client.get_service("AdGroupAdService")

            operation = client.get_type("AdGroupAdOperation")
            ag_ad = operation.create
            ag_ad.ad_group = ad_group_resource
            ag_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

            call_ad = ag_ad.ad.call_ad
            call_ad.country_code = ad_data.get("country_code", "US")
            call_ad.phone_number = ad_data.get("phone_number", "")
            call_ad.business_name = ad_data.get("business_name", "")[:25]
            call_ad.headline1 = ad_data.get("headline1", "")[:30]
            call_ad.headline2 = ad_data.get("headline2", "")[:30]
            call_ad.description1 = ad_data.get("description1", "")[:35]
            call_ad.description2 = ad_data.get("description2", "")[:35]
            call_ad.call_tracked = True
            call_ad.disable_call_conversion = False

            if ad_data.get("phone_number_verification_url"):
                call_ad.phone_number_verification_url = ad_data["phone_number_verification_url"]

            # Final URLs are required even for call ads (used for verification)
            final_urls = ad_data.get("final_urls") or []
            if not final_urls and ad_data.get("final_url"):
                final_urls = [ad_data["final_url"]]
            if not final_urls:
                final_urls = ["https://www.nyblocksmith.com"]
            ag_ad.ad.final_urls.extend(final_urls)

            response = ag_ad_service.mutate_ad_group_ads(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"ad_resource": response.results[0].resource_name, "status": "created"}
        except Exception as e:
            logger.error("Failed to create call ad", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_responsive_display_ad(self, ad_group_resource: str, ad_data: Dict) -> Dict[str, Any]:
        """Create a Responsive Display Ad for Display campaigns."""
        await self._ensure_token()
        try:
            client = self._get_client()
            ag_ad_service = client.get_service("AdGroupAdService")

            operation = client.get_type("AdGroupAdOperation")
            ag_ad = operation.create
            ag_ad.ad_group = ad_group_resource
            ag_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED
            ag_ad.ad.final_urls.extend(ad_data.get("final_urls", []))

            rda = ag_ad.ad.responsive_display_ad

            # Short headlines (up to 5, ≤30 chars each)
            for headline in ad_data.get("short_headlines", [])[:5]:
                h = client.get_type("AdTextAsset")
                h.text = headline[:30]
                rda.headlines.append(h)

            # Long headline (1, ≤90 chars)
            long_hl = ad_data.get("long_headline", "")
            if long_hl:
                rda.long_headline.text = long_hl[:90]

            # Descriptions (up to 5, ≤90 chars each)
            for desc in ad_data.get("descriptions", [])[:5]:
                d = client.get_type("AdTextAsset")
                d.text = desc[:90]
                rda.descriptions.append(d)

            # Business name (≤25 chars)
            if ad_data.get("business_name"):
                rda.business_name = ad_data["business_name"][:25]

            # Image assets (resource names of previously uploaded images)
            for img_resource in ad_data.get("image_asset_resources", []):
                img = client.get_type("AdImageAsset")
                img.asset = img_resource
                rda.marketing_images.append(img)

            # Logo assets
            for logo_resource in ad_data.get("logo_asset_resources", []):
                logo = client.get_type("AdImageAsset")
                logo.asset = logo_resource
                rda.logo_images.append(logo)

            response = ag_ad_service.mutate_ad_group_ads(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"ad_resource": response.results[0].resource_name, "status": "created"}
        except Exception as e:
            logger.error("Failed to create responsive display ad", error=str(e))
            return {"status": "error", "error": str(e)}

    # ── PERFORMANCE MAX ASSET GROUP METHODS ────────────────────────────

    async def create_asset_group(
        self, campaign_resource: str, asset_group_data: Dict
    ) -> Dict[str, Any]:
        """Create a PMax Asset Group with final URL and name."""
        await self._ensure_token()
        try:
            client = self._get_client()
            ag_service = client.get_service("AssetGroupService")

            operation = client.get_type("AssetGroupOperation")
            ag = operation.create
            ag.name = asset_group_data["name"]
            ag.campaign = campaign_resource
            ag.status = client.enums.AssetGroupStatusEnum.ENABLED

            final_url = asset_group_data.get("final_url", "")
            if final_url:
                ag.final_urls.append(final_url)
            ag.final_mobile_urls.extend(asset_group_data.get("final_mobile_urls", []))

            response = ag_service.mutate_asset_groups(
                customer_id=self.customer_id, operations=[operation]
            )
            return {
                "asset_group_resource": response.results[0].resource_name,
                "status": "created",
            }
        except Exception as e:
            logger.error("Failed to create asset group", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_asset_group_assets(
        self, asset_group_resource: str, text_assets: Dict
    ) -> Dict[str, Any]:
        """
        Create and link text assets (headlines, descriptions, long headlines, business name)
        to a PMax Asset Group. Uses batch operations: create Asset → link via AssetGroupAsset.
        """
        await self._ensure_token()
        try:
            client = self._get_client()
            asset_service = client.get_service("AssetService")
            aga_service = client.get_service("AssetGroupAssetService")

            created_assets = []

            # Helper: create a text asset and link it to the asset group
            async def _create_and_link(text: str, field_type_enum):
                # Create the asset
                asset_op = client.get_type("AssetOperation")
                asset = asset_op.create
                asset.text_asset.text = text
                asset.name = f"PMax - {text[:30]}"

                asset_response = asset_service.mutate_assets(
                    customer_id=self.customer_id, operations=[asset_op]
                )
                asset_resource = asset_response.results[0].resource_name

                # Link to asset group
                link_op = client.get_type("AssetGroupAssetOperation")
                link = link_op.create
                link.asset = asset_resource
                link.asset_group = asset_group_resource
                link.field_type = field_type_enum

                aga_service.mutate_asset_group_assets(
                    customer_id=self.customer_id, operations=[link_op]
                )
                created_assets.append({"asset": asset_resource, "type": field_type_enum.name})

            field_types = client.enums.AssetFieldTypeEnum

            # Headlines (≤30 chars, up to 15)
            for headline in text_assets.get("headlines", [])[:15]:
                await _create_and_link(headline[:30], field_types.HEADLINE)

            # Long headlines (≤90 chars, up to 5)
            for lh in text_assets.get("long_headlines", [])[:5]:
                await _create_and_link(lh[:90], field_types.LONG_HEADLINE)

            # Descriptions (≤90 chars, up to 5)
            for desc in text_assets.get("descriptions", [])[:5]:
                await _create_and_link(desc[:90], field_types.DESCRIPTION)

            # Business name (≤25 chars)
            biz_name = text_assets.get("business_name", "")
            if biz_name:
                await _create_and_link(biz_name[:25], field_types.BUSINESS_NAME)

            return {"status": "created", "assets_linked": len(created_assets), "details": created_assets}
        except Exception as e:
            logger.error("Failed to create asset group assets", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_asset_group_signal(
        self, asset_group_resource: str, signal_data: Dict
    ) -> Dict[str, Any]:
        """Add audience signals (search themes) to a PMax Asset Group."""
        await self._ensure_token()
        try:
            client = self._get_client()
            agsi_service = client.get_service("AssetGroupSignalService")

            operation = client.get_type("AssetGroupSignalOperation")
            signal = operation.create
            signal.asset_group = asset_group_resource

            # Add search theme signals
            search_themes = signal_data.get("search_themes", [])
            for theme in search_themes[:10]:
                st = client.get_type("SearchThemeInfo")
                st.text = theme[:255]
                signal.search_theme = st

                # Each search theme is a separate signal — mutate one at a time
                agsi_service.mutate_asset_group_signals(
                    customer_id=self.customer_id, operations=[operation]
                )
                # Reset for next
                operation = client.get_type("AssetGroupSignalOperation")
                signal = operation.create
                signal.asset_group = asset_group_resource

            return {"status": "created", "search_themes_added": len(search_themes)}
        except Exception as e:
            logger.error("Failed to create asset group signal", error=str(e))
            return {"status": "error", "error": str(e)}

    # ── ASSET / EXTENSION METHODS ───────────────────────────────────

    async def list_assets(self, asset_types: List[str] = None) -> List[Dict[str, Any]]:
        """List existing assets in the Google Ads account.
        asset_types: filter by type e.g. ["IMAGE", "SITELINK", "CALLOUT"]
        If None, returns all image and text assets.
        """
        await self._ensure_token()
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")

            type_filter = ""
            if asset_types:
                types_str = ", ".join(f"'{t}'" for t in asset_types)
                type_filter = f"AND asset.type IN ({types_str})"

            query = f"""
                SELECT asset.id, asset.name, asset.type,
                       asset.image_asset.file_size, asset.image_asset.full_size.url,
                       asset.image_asset.full_size.width_pixels, asset.image_asset.full_size.height_pixels,
                       asset.text_asset.text,
                       asset.sitelink_asset.link_text, asset.sitelink_asset.description1,
                       asset.callout_asset.callout_text
                FROM asset
                WHERE asset.type IN ('IMAGE', 'SITELINK', 'CALLOUT', 'STRUCTURED_SNIPPET', 'PROMOTION')
                {type_filter}
                ORDER BY asset.id DESC
                LIMIT 100
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            assets = []
            for row in response:
                a = row.asset
                asset_data = {
                    "asset_id": str(a.id),
                    "name": a.name,
                    "type": a.type_.name,
                    "resource_name": a.resource_name,
                }
                if a.type_.name == "IMAGE":
                    try:
                        asset_data["image_url"] = a.image_asset.full_size.url
                        asset_data["width"] = a.image_asset.full_size.width_pixels
                        asset_data["height"] = a.image_asset.full_size.height_pixels
                        asset_data["file_size"] = a.image_asset.file_size
                    except Exception:
                        pass
                elif a.type_.name == "SITELINK":
                    try:
                        asset_data["link_text"] = a.sitelink_asset.link_text
                        asset_data["description1"] = a.sitelink_asset.description1
                    except Exception:
                        pass
                elif a.type_.name == "CALLOUT":
                    try:
                        asset_data["callout_text"] = a.callout_asset.callout_text
                    except Exception:
                        pass
                assets.append(asset_data)
            return assets
        except Exception as e:
            logger.error("Failed to list assets", error=str(e))
            return []

    async def create_sitelink_assets(self, campaign_id: str, sitelinks: List[Dict]) -> Dict[str, Any]:
        """Create sitelink assets and link them to a campaign.
        Each sitelink: {"link_text": str, "final_url": str, "description1": str, "description2": str}
        """
        await self._ensure_token()
        try:
            client = self._get_client()
            asset_service = client.get_service("AssetService")
            ca_service = client.get_service("CampaignAssetService")
            results = []

            for sl in sitelinks:
                # Create the sitelink asset
                asset_op = client.get_type("AssetOperation")
                asset = asset_op.create
                asset.sitelink_asset.link_text = sl.get("link_text", "")[:25]
                asset.sitelink_asset.description1 = sl.get("description1", "")[:35]
                asset.sitelink_asset.description2 = sl.get("description2", "")[:35]
                asset.final_urls.append(sl.get("final_url", ""))

                resp = asset_service.mutate_assets(
                    customer_id=self.customer_id, operations=[asset_op]
                )
                asset_resource = resp.results[0].resource_name

                # Link to campaign
                link_op = client.get_type("CampaignAssetOperation")
                link = link_op.create
                link.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
                link.asset = asset_resource
                link.field_type = client.enums.AssetFieldTypeEnum.SITELINK

                ca_service.mutate_campaign_assets(
                    customer_id=self.customer_id, operations=[link_op]
                )
                results.append({"link_text": sl.get("link_text"), "status": "created"})

            return {"status": "success", "sitelinks_created": len(results), "details": results}
        except Exception as e:
            logger.error("Failed to create sitelinks", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_callout_assets(self, campaign_id: str, callouts: List[str]) -> Dict[str, Any]:
        """Create callout assets and link them to a campaign.
        Each callout is a string (max 25 chars), e.g. ["Free Estimates", "24/7 Service"]
        """
        await self._ensure_token()
        try:
            client = self._get_client()
            asset_service = client.get_service("AssetService")
            ca_service = client.get_service("CampaignAssetService")
            created = 0

            for text in callouts:
                asset_op = client.get_type("AssetOperation")
                asset_op.create.callout_asset.callout_text = text[:25]

                resp = asset_service.mutate_assets(
                    customer_id=self.customer_id, operations=[asset_op]
                )
                asset_resource = resp.results[0].resource_name

                link_op = client.get_type("CampaignAssetOperation")
                link = link_op.create
                link.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
                link.asset = asset_resource
                link.field_type = client.enums.AssetFieldTypeEnum.CALLOUT

                ca_service.mutate_campaign_assets(
                    customer_id=self.customer_id, operations=[link_op]
                )
                created += 1

            return {"status": "success", "callouts_created": created}
        except Exception as e:
            logger.error("Failed to create callouts", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_structured_snippet_assets(
        self, campaign_id: str, header: str, values: List[str]
    ) -> Dict[str, Any]:
        """Create structured snippet assets and link to campaign.
        header: e.g. "Services", "Types", "Brands"
        values: list of snippet values (max 25 chars each)
        """
        await self._ensure_token()
        try:
            client = self._get_client()
            asset_service = client.get_service("AssetService")
            ca_service = client.get_service("CampaignAssetService")

            asset_op = client.get_type("AssetOperation")
            snippet = asset_op.create.structured_snippet_asset
            snippet.header = header
            for v in values:
                snippet.values.append(v[:25])

            resp = asset_service.mutate_assets(
                customer_id=self.customer_id, operations=[asset_op]
            )
            asset_resource = resp.results[0].resource_name

            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET

            ca_service.mutate_campaign_assets(
                customer_id=self.customer_id, operations=[link_op]
            )
            return {"status": "success", "header": header, "values_count": len(values)}
        except Exception as e:
            logger.error("Failed to create structured snippets", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_image_asset(self, image_url: str, asset_name: str) -> Dict[str, Any]:
        """Upload an image from URL and create an image asset.
        Returns the asset resource name for use in ads/extensions.
        """
        import httpx
        import base64
        await self._ensure_token()
        try:
            # Download image
            async with httpx.AsyncClient() as http_client:
                img_resp = await http_client.get(image_url, timeout=30)
                if img_resp.status_code != 200:
                    return {"status": "error", "error": f"Failed to download image: {img_resp.status_code}"}
                image_data = img_resp.content

            client = self._get_client()
            asset_service = client.get_service("AssetService")

            asset_op = client.get_type("AssetOperation")
            asset = asset_op.create
            asset.name = asset_name[:128]
            asset.type_ = client.enums.AssetTypeEnum.IMAGE
            asset.image_asset.data = image_data

            resp = asset_service.mutate_assets(
                customer_id=self.customer_id, operations=[asset_op]
            )
            return {
                "status": "success",
                "asset_resource": resp.results[0].resource_name,
                "name": asset_name,
            }
        except Exception as e:
            logger.error("Failed to create image asset", error=str(e))
            return {"status": "error", "error": str(e)}

    async def link_image_to_campaign(
        self, campaign_id: str, asset_resource: str
    ) -> Dict[str, Any]:
        """Link an existing image asset to a campaign.
        Note: MARKETING_IMAGE is only supported by Display/PMax campaigns,
        not Search campaigns. Skips gracefully for incompatible types."""
        await self._ensure_token()
        try:
            client = self._get_client()

            # Check campaign type first — Search campaigns don't support MARKETING_IMAGE
            ga_service = client.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign.advertising_channel_type
                FROM campaign
                WHERE campaign.id = {campaign_id}
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            for row in response:
                channel_type = row.campaign.advertising_channel_type.name
                if channel_type == "SEARCH":
                    logger.info("Skipping image link — Search campaigns don't support MARKETING_IMAGE",
                        campaign_id=campaign_id)
                    return {"status": "skipped", "reason": "Search campaigns don't support image assets"}

            ca_service = client.get_service("CampaignAssetService")
            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.MARKETING_IMAGE

            ca_service.mutate_campaign_assets(
                customer_id=self.customer_id, operations=[link_op]
            )
            return {"status": "success", "campaign_id": campaign_id}
        except Exception as e:
            logger.error("Failed to link image to campaign", error=str(e))
            return {"status": "error", "error": str(e)}

    async def create_promotion_asset(
        self, campaign_id: str, promotion: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a promotion extension and link to campaign.
        promotion: {"occasion": "NONE", "discount_modifier": "UP_TO",
                     "percent_off": 20, "promotion_target": "Free Key Inspection",
                     "final_url": "https://..."}
        """
        await self._ensure_token()
        try:
            client = self._get_client()
            asset_service = client.get_service("AssetService")
            ca_service = client.get_service("CampaignAssetService")

            asset_op = client.get_type("AssetOperation")
            promo = asset_op.create.promotion_asset
            promo.promotion_target = promotion.get("promotion_target", "")[:20]
            promo.language_code = "en"

            if promotion.get("percent_off"):
                promo.percent_off = promotion["percent_off"]
            elif promotion.get("money_amount_off"):
                promo.money_amount_off.amount_micros = int(promotion["money_amount_off"] * 1_000_000)
                promo.money_amount_off.currency_code = "USD"

            asset_op.create.final_urls.append(promotion.get("final_url", ""))

            resp = asset_service.mutate_assets(
                customer_id=self.customer_id, operations=[asset_op]
            )
            asset_resource = resp.results[0].resource_name

            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.PROMOTION

            ca_service.mutate_campaign_assets(
                customer_id=self.customer_id, operations=[link_op]
            )
            return {"status": "success", "promotion_target": promotion.get("promotion_target")}
        except Exception as e:
            logger.error("Failed to create promotion asset", error=str(e))
            return {"status": "error", "error": str(e)}

    async def deploy_full_campaign(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deploy a complete campaign atomically using GoogleAdsService.Mutate
        with temporary resource names (negative IDs).

        All entities (budget, campaign, ad groups, keywords, ads) are created
        in a SINGLE API call. If any entity fails, NOTHING is created —
        no orphaned campaigns or ad groups.

        Extensions (sitelinks, callouts, snippets) are batched in a second
        call since they require asset creation + campaign linking.
        """
        from google.ads.googleads.errors import GoogleAdsException

        results = {"campaign": None, "ad_groups": [], "errors": []}

        # Pre-validation
        ad_group_specs = spec.get("ad_groups", [])
        asset_group_specs = spec.get("asset_groups", [])
        channel_type = spec.get("campaign", {}).get("channel_type", "SEARCH").upper()
        is_pmax_spec = channel_type == "PERFORMANCE_MAX"

        if not ad_group_specs and not asset_group_specs:
            logger.error("deploy_full_campaign called with no ad groups or asset groups",
                spec_keys=list(spec.keys()))
            return {"status": "error", "error": "No ad groups or asset groups in campaign spec — nothing to deploy"}
        if not ad_group_specs and not is_pmax_spec:
            logger.error("deploy_full_campaign called with zero ad groups for non-PMax campaign",
                spec_keys=list(spec.keys()))
            return {"status": "error", "error": "No ad groups in campaign spec — nothing to deploy"}

        # Log spec summary
        total_kws = 0
        total_ads = 0
        for i, ag in enumerate(ad_group_specs):
            kw_count = len(ag.get("keywords", []))
            ad_count = len(ag.get("ads", []))
            total_kws += kw_count
            total_ads += ad_count
            logger.info("Ad group spec",
                index=i, name=ag.get("name"), keywords=kw_count, ads=ad_count)

        await self._ensure_token()

        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")
            campaign_data = spec.get("campaign", {})

            # ── Build all operations with temporary IDs ──────────────
            operations = []
            BUDGET_TEMP_ID = -1
            CAMPAIGN_TEMP_ID = -2
            next_temp_id = -3  # ad groups start at -3

            # 1. Budget operation
            budget_op = client.get_type("MutateOperation")
            budget = budget_op.campaign_budget_operation.create
            budget.resource_name = ga_service.campaign_budget_path(self.customer_id, str(BUDGET_TEMP_ID))
            budget.name = f"Budget - {campaign_data.get('name', 'Campaign')}"
            budget.amount_micros = campaign_data.get("budget_micros", 30_000_000)
            budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
            budget.explicitly_shared = False
            operations.append(budget_op)

            # 2. Campaign operation
            campaign_op = client.get_type("MutateOperation")
            campaign = campaign_op.campaign_operation.create
            campaign.resource_name = ga_service.campaign_path(self.customer_id, str(CAMPAIGN_TEMP_ID))
            campaign.name = campaign_data.get("name", "New Campaign")
            campaign.campaign_budget = ga_service.campaign_budget_path(self.customer_id, str(BUDGET_TEMP_ID))
            campaign.status = client.enums.CampaignStatusEnum.PAUSED
            campaign.contains_eu_political_advertising = (
                client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
            )

            # Channel type
            channel = campaign_data.get("channel_type", "SEARCH").upper()
            channel_map = {
                "SEARCH": client.enums.AdvertisingChannelTypeEnum.SEARCH,
                "DISPLAY": client.enums.AdvertisingChannelTypeEnum.DISPLAY,
                "PERFORMANCE_MAX": client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX,
                "CALL": client.enums.AdvertisingChannelTypeEnum.SEARCH,
            }
            campaign.advertising_channel_type = channel_map.get(
                channel, client.enums.AdvertisingChannelTypeEnum.SEARCH
            )

            # PMax guard: Performance Max uses asset groups, not ad groups/RSAs
            is_pmax = channel == "PERFORMANCE_MAX"
            if is_pmax:
                logger.info("Performance Max campaign — asset groups will be created post-deploy.")

            # Geo targeting: PRESENCE only (critical for local businesses)
            campaign.geo_target_type_setting.positive_geo_target_type = (
                client.enums.PositiveGeoTargetTypeEnum.PRESENCE
            )
            campaign.geo_target_type_setting.negative_geo_target_type = (
                client.enums.NegativeGeoTargetTypeEnum.PRESENCE
            )

            # Network settings
            if channel in ("SEARCH", "CALL"):
                network = campaign_data.get("network", "SEARCH").upper()
                campaign.network_settings.target_google_search = True
                campaign.network_settings.target_search_network = (network == "ALL")
                campaign.network_settings.target_content_network = False

            # Bidding strategy
            bid_strategy = campaign_data.get("bidding_strategy", "MAXIMIZE_CONVERSIONS").upper()
            if bid_strategy == "MAXIMIZE_CONVERSIONS":
                campaign.maximize_conversions.target_cpa_micros = campaign_data.get("target_cpa_micros", 0)
            elif bid_strategy == "TARGET_CPA":
                campaign.maximize_conversions.target_cpa_micros = campaign_data.get("target_cpa_micros", 25_000_000)
            elif bid_strategy == "MAXIMIZE_CONVERSION_VALUE":
                campaign.maximize_conversion_value.target_roas = campaign_data.get("target_roas", 0)
            elif bid_strategy == "MAXIMIZE_CLICKS":
                campaign.maximize_clicks.cpc_bid_ceiling_micros = campaign_data.get("cpc_ceiling_micros", 0)

            operations.append(campaign_op)

            # 3. Ad groups, keywords, and ads
            # 3. Ad groups, keywords, and ads (skip for PMax — uses asset groups)
            ag_temp_ids = []  # Track temp IDs for result mapping
            all_neg_kws = []  # Collect negative keywords for batch

            # PMax asset groups are deployed after the atomic mutate via
            # _deploy_pmax_asset_groups (needs real campaign resource name).

            for ag_spec in ad_group_specs if not is_pmax else []:
                ag_temp_id = next_temp_id
                next_temp_id -= 1
                ag_temp_ids.append((ag_temp_id, ag_spec.get("name", "")))

                # Ad group operation
                ag_op = client.get_type("MutateOperation")
                ag = ag_op.ad_group_operation.create
                ag.resource_name = ga_service.ad_group_path(self.customer_id, str(ag_temp_id))
                ag.name = ag_spec.get("name", "Ad Group")
                ag.campaign = ga_service.campaign_path(self.customer_id, str(CAMPAIGN_TEMP_ID))
                ag.status = client.enums.AdGroupStatusEnum.ENABLED
                ag_type = ag_spec.get("type", "SEARCH_STANDARD").upper()
                type_map = {
                    "SEARCH_STANDARD": client.enums.AdGroupTypeEnum.SEARCH_STANDARD,
                    "DISPLAY_STANDARD": client.enums.AdGroupTypeEnum.DISPLAY_STANDARD,
                }
                ag.type_ = type_map.get(ag_type, client.enums.AdGroupTypeEnum.SEARCH_STANDARD)
                operations.append(ag_op)

                # Keyword operations
                match_map = {
                    "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
                    "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
                    "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
                }
                for kw in ag_spec.get("keywords", []):
                    kw_op = client.get_type("MutateOperation")
                    criterion = kw_op.ad_group_criterion_operation.create
                    criterion.ad_group = ga_service.ad_group_path(self.customer_id, str(ag_temp_id))
                    criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                    criterion.keyword.text = kw.get("text", kw) if isinstance(kw, dict) else str(kw)
                    criterion.keyword.match_type = match_map.get(
                        kw.get("match_type", "PHRASE") if isinstance(kw, dict) else "PHRASE",
                        client.enums.KeywordMatchTypeEnum.PHRASE,
                    )
                    operations.append(kw_op)

                # RSA operations
                for ad_spec in ag_spec.get("ads", []):
                    headlines = ad_spec.get("headlines", [])
                    descriptions = ad_spec.get("descriptions", [])
                    if len(headlines) < 3 or len(descriptions) < 2:
                        logger.warning("Skipping ad with insufficient content",
                            ad_group=ag_spec.get("name", "?"),
                            headlines=len(headlines), descriptions=len(descriptions),
                            required_headlines=3, required_descriptions=2)
                        continue  # Skip invalid ads

                    ad_op = client.get_type("MutateOperation")
                    ag_ad = ad_op.ad_group_ad_operation.create
                    ag_ad.ad_group = ga_service.ad_group_path(self.customer_id, str(ag_temp_id))
                    ag_ad.status = client.enums.AdGroupAdStatusEnum.ENABLED

                    # Final URLs
                    final_urls = ad_spec.get("final_urls") or []
                    if not final_urls and ad_spec.get("final_url"):
                        final_urls = [ad_spec["final_url"]]
                    if not final_urls:
                        final_urls = [campaign_data.get("final_url", "https://www.example.com")]
                    ag_ad.ad.final_urls.extend(final_urls)

                    # Display path
                    display_path = ad_spec.get("display_path", [])
                    if display_path and len(display_path) >= 1:
                        ag_ad.ad.responsive_search_ad.path1 = str(display_path[0])[:15]
                    if display_path and len(display_path) >= 2:
                        ag_ad.ad.responsive_search_ad.path2 = str(display_path[1])[:15]

                    # Headlines with pinning
                    pin_map = {
                        "HEADLINE_1": client.enums.ServedAssetFieldTypeEnum.HEADLINE_1,
                        "HEADLINE_2": client.enums.ServedAssetFieldTypeEnum.HEADLINE_2,
                        "HEADLINE_3": client.enums.ServedAssetFieldTypeEnum.HEADLINE_3,
                        "DESCRIPTION_1": client.enums.ServedAssetFieldTypeEnum.DESCRIPTION_1,
                        "DESCRIPTION_2": client.enums.ServedAssetFieldTypeEnum.DESCRIPTION_2,
                    }

                    import re
                    _phone_re = re.compile(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
                    for headline in headlines[:15]:
                        text = headline if isinstance(headline, str) else headline.get("text", "") if isinstance(headline, dict) else str(headline)
                        text = _phone_re.sub('', text).strip()
                        text = re.sub(r'\s{2,}', ' ', text)
                        if not text:
                            continue
                        h = client.get_type("AdTextAsset")
                        h.text = text[:30]
                        if isinstance(headline, dict) and headline.get("pinned_position"):
                            pin_enum = pin_map.get(headline["pinned_position"].upper())
                            if pin_enum:
                                h.pinned_field = pin_enum
                        ag_ad.ad.responsive_search_ad.headlines.append(h)

                    for desc in descriptions[:4]:
                        text = desc if isinstance(desc, str) else desc.get("text", "") if isinstance(desc, dict) else str(desc)
                        text = _phone_re.sub('', text).strip()
                        text = re.sub(r'\s{2,}', ' ', text)
                        if not text:
                            continue
                        d = client.get_type("AdTextAsset")
                        d.text = text[:90]
                        if isinstance(desc, dict) and desc.get("pinned_position"):
                            pin_enum = pin_map.get(desc["pinned_position"].upper())
                            if pin_enum:
                                d.pinned_field = pin_enum
                        ag_ad.ad.responsive_search_ad.descriptions.append(d)

                    operations.append(ad_op)

                # Collect negative keywords
                neg_kws = ag_spec.get("negative_keywords", [])
                if neg_kws:
                    all_neg_kws.extend(neg_kws)

            # 4. Negative keywords (campaign-level)
            # Merge ad-group negatives + explicit campaign negatives
            # Normalize to strings first (negatives can be str or dict)
            campaign_negatives = set()
            for nk in all_neg_kws:
                text = nk.get("text", "") if isinstance(nk, dict) else str(nk)
                if text.strip():
                    campaign_negatives.add(text.strip())
            for cn in spec.get("campaign_negative_keywords", []):
                text = cn.get("text", cn) if isinstance(cn, dict) else str(cn)
                if text.strip():
                    campaign_negatives.add(text.strip())

            for nk_text in campaign_negatives:
                nk_op = client.get_type("MutateOperation")
                criterion = nk_op.campaign_criterion_operation.create
                criterion.campaign = ga_service.campaign_path(self.customer_id, str(CAMPAIGN_TEMP_ID))
                criterion.negative = True
                criterion.keyword.text = nk_text
                criterion.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
                operations.append(nk_op)

            # ── Execute atomic mutate ────────────────────────────────
            logger.info("Executing atomic campaign deploy",
                operations=len(operations), ad_groups=len(ag_temp_ids),
                keywords=total_kws, ads=total_ads)

            try:
                response = await self._run_sync(
                    ga_service.mutate,
                    customer_id=self.customer_id,
                    mutate_operations=operations,
                )
            except GoogleAdsException as ex:
                errors = self._extract_google_ads_errors(ex)

                # ── Policy violation retry: collect exemption keys and retry ──
                # Trademark keywords (e.g. "Land Rover") trigger POLICY_ERROR
                # that can be exempted for legitimate service providers.
                exemption_keys = []
                for err in errors:
                    ek = err.get("exemption_key")
                    if ek and err.get("is_exemptible"):
                        exemption_keys.append(ek)

                if exemption_keys and not spec.get("_policy_retry_done"):
                    spec["_policy_retry_done"] = True
                    logger.warning("Policy violations detected — retrying with exemptions",
                        exemptible=len(exemption_keys),
                        total_errors=len(errors),
                        request_id=ex.request_id)

                    # Build exemption keys for keyword operations only.
                    # RSA ads do NOT support exempt_policy_violation_keys —
                    # they go through review automatically once keywords are exempted.
                    for op in operations:
                        if op._pb.HasField("ad_group_criterion_operation"):
                            for ek in exemption_keys:
                                key = client.get_type("PolicyViolationKey")
                                key.policy_name = ek["policy_name"]
                                key.violating_text = ek["violating_text"]
                                op.ad_group_criterion_operation.exempt_policy_violation_keys.append(key)

                    try:
                        response = await self._run_sync(
                            ga_service.mutate,
                            customer_id=self.customer_id,
                            mutate_operations=operations,
                        )
                        logger.info("Policy exemption retry succeeded",
                            exemptions=len(exemption_keys))
                    except GoogleAdsException as retry_ex:
                        retry_errors = self._extract_google_ads_errors(retry_ex)
                        logger.error("Policy exemption retry also failed",
                            errors=retry_errors[:5], request_id=retry_ex.request_id)
                        return {
                            "status": "error",
                            "error": f"Google Ads policy error (even with exemptions): {retry_errors[0]['message'] if retry_errors else str(retry_ex)}",
                            "errors": retry_errors,
                            "request_id": retry_ex.request_id,
                        }
                else:
                    logger.error("Atomic campaign deploy failed",
                        errors=errors, request_id=ex.request_id)
                    return {
                        "status": "error",
                        "error": f"Google Ads API error: {errors[0]['message'] if errors else str(ex)}",
                        "errors": errors,
                        "request_id": ex.request_id,
                    }

            # ── Parse response ───────────────────────────────────────
            # The response contains results in the SAME ORDER as operations
            campaign_resource = None
            campaign_id = None

            # Find the campaign result (it's the 2nd operation, index 1)
            for i, result in enumerate(response.mutate_operation_responses):
                if result.campaign_result.resource_name:
                    campaign_resource = result.campaign_result.resource_name
                    campaign_id = campaign_resource.split("/")[-1]
                    break

            if not campaign_id:
                return {"status": "error", "error": "Campaign creation succeeded but could not extract campaign ID"}

            results["campaign"] = {
                "campaign_resource": campaign_resource,
                "campaign_id": campaign_id,
                "status": "created",
            }

            # Count created entities
            kw_created = 0
            ads_created = 0
            ag_created = 0
            for result in response.mutate_operation_responses:
                if result.ad_group_result.resource_name:
                    ag_created += 1
                elif result.ad_group_criterion_result.resource_name:
                    kw_created += 1
                elif result.ad_group_ad_result.resource_name:
                    ads_created += 1

            results["ad_groups"] = [
                {"name": name, "keywords": "batched", "ads": "batched"}
                for _, name in ag_temp_ids
            ]

            # Check partial failures
            if response.partial_failure_error:
                from google.ads.googleads.v23.errors.types.errors import GoogleAdsFailure
                failure = GoogleAdsFailure()
                failure._pb.MergeFrom(response.partial_failure_error)
                for error in failure.errors:
                    results["errors"].append(error.message)
                    logger.warning("Atomic deploy partial failure", message=error.message)

            logger.info("Atomic campaign deploy complete",
                campaign_id=campaign_id,
                ad_groups=ag_created, keywords=kw_created, ads=ads_created,
                partial_failures=len(results["errors"]))

            # ── Extensions (second batch — needs real campaign ID) ────
            await self._deploy_extensions_batched(client, campaign_id, spec, results)

            # ── PMax: Create asset groups (third batch — needs real campaign resource) ──
            if is_pmax and spec.get("asset_groups"):
                await self._deploy_pmax_asset_groups(campaign_resource, spec, results)

            # ── Post-deploy: Apply targeting settings ────────────────
            await self._apply_targeting_settings(campaign_id, spec, results)

            # ── Post-deploy: Assign conversion actions ───────────────
            try:
                conv_action_ids = spec.get("conversion_action_ids", [])
                if not conv_action_ids:
                    # Auto-select best conversion actions
                    best_actions = await self.select_best_conversion_actions()
                    conv_action_ids = [a["action_id"] for a in best_actions]
                if conv_action_ids:
                    conv_result = await self.set_campaign_conversion_goals(
                        campaign_id, conv_action_ids
                    )
                    results["conversion_goals"] = conv_result
                    logger.info("Conversion goals assigned",
                        campaign_id=campaign_id,
                        actions=len(conv_action_ids))
            except Exception as conv_err:
                logger.warning("Conversion goal assignment failed",
                    error=str(conv_err))

            # ── Post-deploy: Link GBP location asset ─────────────────
            gbp_place_id = spec.get("gbp_place_id", "")
            gbp_account_id = spec.get("gbp_account_id", "")
            if gbp_place_id:
                try:
                    location_result = await self.link_gbp_location_asset(
                        campaign_id, gbp_account_id, gbp_place_id
                    )
                    results["location_asset"] = location_result
                    if location_result.get("status") == "success":
                        logger.info("GBP location linked", campaign_id=campaign_id)
                except Exception as loc_err:
                    logger.warning("GBP location linking failed", error=str(loc_err))

            results["status"] = "success" if not results["errors"] else "partial"
            results["total_operations"] = len(operations)
            results["summary"] = {
                "ad_groups": ag_created,
                "keywords": kw_created,
                "ads": ads_created,
            }
            return results

        except GoogleAdsException as ex:
            errors = self._extract_google_ads_errors(ex)
            logger.error("Full campaign deploy failed (GoogleAds)", errors=errors)
            return {"status": "error", "error": str(ex), "errors": errors}
        except Exception as e:
            logger.error("Full campaign deploy failed", error=str(e))
            return {"status": "error", "error": str(e), "partial_results": results}

    async def _deploy_extensions_batched(
        self, client, campaign_id: str, spec: Dict, results: Dict
    ) -> None:
        """
        Deploy all extensions (sitelinks, callouts, snippets) in batched API calls.
        Two calls: one batch for asset creation, one batch for campaign linking.
        """
        from google.ads.googleads.errors import GoogleAdsException

        asset_service = client.get_service("AssetService")
        ca_service = client.get_service("CampaignAssetService")
        campaign_resource = f"customers/{self.customer_id}/campaigns/{campaign_id}"

        # ── Batch 1: Create all assets ───────────────────────────
        asset_operations = []
        asset_types = []  # Track type for linking step

        # Sitelinks
        for sl in spec.get("sitelinks", []):
            asset_op = client.get_type("AssetOperation")
            asset = asset_op.create
            asset.sitelink_asset.link_text = sl.get("link_text", "")[:25]
            asset.sitelink_asset.description1 = sl.get("description1", "")[:35]
            asset.sitelink_asset.description2 = sl.get("description2", "")[:35]
            asset.final_urls.append(sl.get("final_url", ""))
            asset_operations.append(asset_op)
            asset_types.append("SITELINK")

        # Callouts
        for text in spec.get("callouts", []):
            asset_op = client.get_type("AssetOperation")
            asset_op.create.callout_asset.callout_text = str(text)[:25]
            asset_operations.append(asset_op)
            asset_types.append("CALLOUT")

        # Structured snippets
        snippets = spec.get("structured_snippets")
        if snippets and snippets.get("header") and snippets.get("values"):
            asset_op = client.get_type("AssetOperation")
            snippet = asset_op.create.structured_snippet_asset
            snippet.header = snippets["header"]
            for v in snippets["values"]:
                snippet.values.append(str(v)[:25])
            asset_operations.append(asset_op)
            asset_types.append("STRUCTURED_SNIPPET")

        # Promotion extensions
        for promo in spec.get("promotion_extensions", []):
            try:
                asset_op = client.get_type("AssetOperation")
                promo_asset = asset_op.create.promotion_asset
                promo_asset.promotion_target = str(promo.get("promotion_target", ""))[:20]
                promo_asset.language_code = "en"
                promo_asset.redemption_start_date = promo.get("start_date", "")
                promo_asset.redemption_end_date = promo.get("end_date", "")

                if promo.get("percent_off"):
                    promo_asset.percent_off = int(promo["percent_off"])
                    promo_asset.discount_modifier = (
                        client.enums.PromotionExtensionDiscountModifierEnum.UP_TO
                    )
                elif promo.get("money_off_micros"):
                    promo_asset.money_amount_off.amount_micros = int(promo["money_off_micros"])
                    promo_asset.money_amount_off.currency_code = "USD"

                promo_asset.occasion = (
                    client.enums.PromotionExtensionOccasionEnum.NONE
                )

                asset_op.create.final_urls.append(promo.get("final_url", ""))
                asset_operations.append(asset_op)
                asset_types.append("PROMOTION")
            except Exception as promo_err:
                logger.warning("Promotion extension failed to build", error=str(promo_err))

        if not asset_operations:
            return

        # Execute batch asset creation
        try:
            asset_response = await self._run_sync(
                asset_service.mutate_assets,
                customer_id=self.customer_id,
                operations=asset_operations,
                partial_failure=True,
            )
        except GoogleAdsException as ex:
            errors = self._extract_google_ads_errors(ex)
            results["errors"].append(f"Extension assets: {errors[0]['message'] if errors else str(ex)}")
            return

        # ── Batch 2: Link all assets to campaign ─────────────────
        field_type_map = {
            "SITELINK": client.enums.AssetFieldTypeEnum.SITELINK,
            "CALLOUT": client.enums.AssetFieldTypeEnum.CALLOUT,
            "STRUCTURED_SNIPPET": client.enums.AssetFieldTypeEnum.STRUCTURED_SNIPPET,
            "PROMOTION": client.enums.AssetFieldTypeEnum.PROMOTION,
        }

        link_operations = []
        for i, result in enumerate(asset_response.results):
            if not result.resource_name:
                continue
            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = campaign_resource
            link.asset = result.resource_name
            link.field_type = field_type_map.get(
                asset_types[i], client.enums.AssetFieldTypeEnum.SITELINK
            )
            link_operations.append(link_op)

        if not link_operations:
            return

        try:
            await self._run_sync(
                ca_service.mutate_campaign_assets,
                customer_id=self.customer_id,
                operations=link_operations,
                partial_failure=True,
            )
            sitelink_count = sum(1 for t in asset_types if t == "SITELINK")
            callout_count = sum(1 for t in asset_types if t == "CALLOUT")
            if sitelink_count:
                results["sitelinks"] = sitelink_count
            if callout_count:
                results["callouts"] = callout_count
            if any(t == "STRUCTURED_SNIPPET" for t in asset_types):
                results["structured_snippets"] = True

            logger.info("Extensions deployed",
                sitelinks=sitelink_count, callouts=callout_count,
                snippets=1 if snippets else 0)
        except GoogleAdsException as ex:
            errors = self._extract_google_ads_errors(ex)
            results["errors"].append(f"Extension linking: {errors[0]['message'] if errors else str(ex)}")

    async def _deploy_pmax_asset_groups(
        self, campaign_resource: str, spec: Dict, results: Dict
    ) -> None:
        """
        Deploy Performance Max asset groups with text assets, listing group
        filter, and audience signals (search themes).

        Each asset group in spec["asset_groups"] contains:
        - name, final_url, headlines[], long_headlines[], descriptions[],
          business_name, search_themes[], images[]
        """
        from google.ads.googleads.errors import GoogleAdsException

        asset_groups_deployed = []
        for ag_spec in spec.get("asset_groups", []):
            try:
                # Step 1: Create the asset group
                ag_result = await self.create_asset_group(
                    campaign_resource=campaign_resource,
                    asset_group_data={
                        "name": ag_spec.get("name", "Asset Group"),
                        "final_url": ag_spec.get("final_url", ""),
                    },
                )
                if ag_result.get("status") == "error":
                    results["errors"].append(
                        f"Asset group '{ag_spec.get('name')}': {ag_result.get('error', 'unknown')}"
                    )
                    continue

                ag_resource = ag_result["asset_group_resource"]

                # Step 2: Create and link text assets
                text_result = await self.create_asset_group_assets(
                    asset_group_resource=ag_resource,
                    text_assets={
                        "headlines": ag_spec.get("headlines", []),
                        "long_headlines": ag_spec.get("long_headlines", []),
                        "descriptions": ag_spec.get("descriptions", []),
                        "business_name": ag_spec.get("business_name", ""),
                    },
                )
                if text_result.get("status") == "error":
                    results["errors"].append(
                        f"Asset group assets '{ag_spec.get('name')}': {text_result.get('error', 'unknown')}"
                    )

                # Step 3: Create listing group filter (required for PMax)
                await self._create_listing_group_filter(ag_resource)

                # Step 4: Add audience signals (search themes)
                search_themes = ag_spec.get("search_themes", [])
                if search_themes:
                    signal_result = await self.create_asset_group_signal(
                        asset_group_resource=ag_resource,
                        signal_data={"search_themes": search_themes},
                    )
                    if signal_result.get("status") == "error":
                        logger.warning("Asset group signals failed",
                            error=signal_result.get("error"),
                            asset_group=ag_spec.get("name"))

                # Step 5: Upload and link image assets if available
                images = ag_spec.get("images", [])
                if images:
                    resolved_images = []
                    for img in images:
                        # If the pipeline provided a URL instead of an asset_resource,
                        # upload the image first to get the asset resource name.
                        if img.get("url") and not img.get("asset_resource"):
                            upload_result = await self.create_image_asset(
                                image_url=img["url"],
                                asset_name=f"pmax_{ag_spec.get('name', 'img')}_{len(resolved_images)}",
                            )
                            if upload_result.get("status") == "success":
                                resolved_images.append({
                                    "asset_resource": upload_result["asset_resource"],
                                    "field_type": img.get("field_type", "MARKETING_IMAGE"),
                                })
                            else:
                                logger.warning("Image upload failed for asset group",
                                    url=img["url"], error=upload_result.get("error"))
                        else:
                            resolved_images.append(img)
                    if resolved_images:
                        await self._link_image_assets_to_asset_group(ag_resource, resolved_images)

                asset_groups_deployed.append({
                    "name": ag_spec.get("name"),
                    "resource": ag_resource,
                    "assets_linked": text_result.get("assets_linked", 0),
                    "search_themes": len(search_themes),
                })

            except Exception as e:
                logger.error("PMax asset group deploy failed",
                    asset_group=ag_spec.get("name"), error=str(e))
                results["errors"].append(f"Asset group '{ag_spec.get('name')}': {str(e)}")

        results["asset_groups"] = asset_groups_deployed
        results["summary"]["asset_groups"] = len(asset_groups_deployed)
        logger.info("PMax asset groups deployed",
            count=len(asset_groups_deployed),
            errors=len(results.get("errors", [])))

    async def _create_listing_group_filter(self, asset_group_resource: str) -> Dict:
        """
        Create a default listing group filter for a PMax asset group.
        This is the 'All products' / 'Everything else' filter that PMax requires.
        Without it, the asset group won't serve.
        """
        try:
            await self._ensure_token()
            client = self._get_client()
            aglgf_service = client.get_service("AssetGroupListingGroupFilterService")

            operation = client.get_type("AssetGroupListingGroupFilterOperation")
            listing_filter = operation.create
            listing_filter.asset_group = asset_group_resource
            listing_filter.type_ = client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED

            # SHOPPING vertical is required even for non-shopping PMax (per Google Ads API docs)
            # This root node means "all listings included"
            listing_filter.vertical = client.enums.ListingGroupFilterVerticalEnum.SHOPPING

            response = aglgf_service.mutate_asset_group_listing_group_filters(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": "created", "resource": response.results[0].resource_name}
        except Exception as e:
            # Non-fatal: some campaigns work without explicit listing group
            logger.warning("Listing group filter creation failed", error=str(e))
            return {"status": "skipped", "error": str(e)}

    async def _link_image_assets_to_asset_group(
        self, asset_group_resource: str, images: List[Dict]
    ) -> None:
        """
        Link existing image assets to a PMax asset group.
        images: [{"asset_resource": "customers/123/assets/456", "field_type": "MARKETING_IMAGE"}]
        """
        try:
            await self._ensure_token()
            client = self._get_client()
            aga_service = client.get_service("AssetGroupAssetService")

            field_type_map = {
                "MARKETING_IMAGE": client.enums.AssetFieldTypeEnum.MARKETING_IMAGE,
                "SQUARE_MARKETING_IMAGE": client.enums.AssetFieldTypeEnum.SQUARE_MARKETING_IMAGE,
                "LOGO": client.enums.AssetFieldTypeEnum.LOGO,
                "LANDSCAPE_LOGO": client.enums.AssetFieldTypeEnum.LANDSCAPE_LOGO,
                "PORTRAIT_MARKETING_IMAGE": client.enums.AssetFieldTypeEnum.PORTRAIT_MARKETING_IMAGE,
            }

            operations = []
            for img in images:
                asset_resource = img.get("asset_resource", "")
                field_type = img.get("field_type", "MARKETING_IMAGE")
                if not asset_resource:
                    continue

                link_op = client.get_type("AssetGroupAssetOperation")
                link = link_op.create
                link.asset = asset_resource
                link.asset_group = asset_group_resource
                link.field_type = field_type_map.get(
                    field_type, client.enums.AssetFieldTypeEnum.MARKETING_IMAGE
                )
                operations.append(link_op)

            if operations:
                aga_service.mutate_asset_group_assets(
                    customer_id=self.customer_id, operations=operations
                )
                logger.info("Image assets linked to asset group",
                    count=len(operations))
        except Exception as e:
            logger.warning("Image asset linking failed", error=str(e))

    # ── LOCATION ASSETS (GBP) ────────────────────────────────

    async def link_gbp_location_asset(
        self, campaign_id: str, gbp_account_id: str, gbp_location_id: str
    ) -> Dict[str, Any]:
        """
        Link a Google Business Profile location as a location asset on the campaign.
        This enables location extensions showing business address, hours, directions.

        Requires the GBP account to be linked to the Google Ads account first.
        """
        try:
            await self._ensure_token()
            client = self._get_client()

            # Create location asset from GBP
            asset_service = client.get_service("AssetService")
            asset_op = client.get_type("AssetOperation")
            asset = asset_op.create
            asset.location_asset.place_id = gbp_location_id  # Google Places ID

            try:
                asset_response = await self._run_sync(
                    asset_service.mutate_assets,
                    customer_id=self.customer_id,
                    operations=[asset_op],
                )
                asset_resource = asset_response.results[0].resource_name
            except Exception as asset_err:
                # Location asset might already exist — try to find it
                ga_service = client.get_service("GoogleAdsService")
                query = """
                    SELECT asset.id, asset.resource_name, asset.type
                    FROM asset
                    WHERE asset.type = 'LOCATION'
                    LIMIT 1
                """
                try:
                    response = await self._run_sync(
                        ga_service.search, customer_id=self.customer_id, query=query
                    )
                    for row in response:
                        asset_resource = row.asset.resource_name
                        break
                    else:
                        return {"status": "error", "error": f"Could not create or find location asset: {str(asset_err)}"}
                except Exception:
                    return {"status": "error", "error": str(asset_err)}

            # Link location asset to campaign
            ca_service = client.get_service("CampaignAssetService")
            campaign_resource = f"customers/{self.customer_id}/campaigns/{campaign_id}"

            link_op = client.get_type("CampaignAssetOperation")
            link = link_op.create
            link.campaign = campaign_resource
            link.asset = asset_resource
            link.field_type = client.enums.AssetFieldTypeEnum.LOCATION

            await self._run_sync(
                ca_service.mutate_campaign_assets,
                customer_id=self.customer_id,
                operations=[link_op],
                partial_failure=True,
            )

            logger.info("GBP location asset linked to campaign",
                campaign_id=campaign_id, place_id=gbp_location_id)
            return {"status": "success", "asset_resource": asset_resource}
        except Exception as e:
            logger.warning("GBP location asset linking failed",
                campaign_id=campaign_id, error=str(e))
            return {"status": "error", "error": str(e)}

    # ── GEO RESOLUTION HELPERS ────────────────────────────────

    async def _resolve_geo_locations(self, location_names: list) -> list:
        """Resolve city/location names to Google Ads geo target criterion IDs."""
        try:
            await self._ensure_token()
            client = self._get_client()
            gtc_service = client.get_service("GeoTargetConstantService")

            resolved = []
            for name in location_names[:10]:
                try:
                    request = client.get_type("SuggestGeoTargetConstantsRequest")
                    request.locale = "en"
                    request.country_code = "US"
                    request.location_names.names.append(name)

                    response = await self._run_sync(
                        gtc_service.suggest_geo_target_constants, request=request,
                    )
                    for suggestion in response.geo_target_constant_suggestions:
                        gtc = suggestion.geo_target_constant
                        resolved.append({
                            "name": gtc.name,
                            "criterion_id": gtc.id,
                            "target_type": gtc.target_type,
                            "canonical_name": gtc.canonical_name,
                            "search_term": name,
                        })
                        break  # Take first (best) match
                except Exception as e:
                    logger.warning("Geo target resolution failed for location",
                        location=name, error=str(e))
            return resolved
        except Exception as e:
            logger.warning("Geo location resolution failed", error=str(e))
            return []

    async def resolve_geo_criterion_ids(self, criterion_ids: List[str]) -> Dict[str, str]:
        """
        Resolve geo target criterion IDs to human-readable names.
        Uses geo_target_constant GAQL query for batch lookup.
        Returns: {criterion_id: canonical_name}
        """
        if not criterion_ids:
            return {}

        try:
            await self._ensure_token()
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")

            # Deduplicate and filter empty
            unique_ids = list(set(cid for cid in criterion_ids if cid and cid != "0"))
            if not unique_ids:
                return {}

            # Query geo_target_constant (this is an account-less query)
            # Build ID filter — batch up to 100 at a time
            result_map = {}
            for batch_start in range(0, len(unique_ids), 100):
                batch = unique_ids[batch_start:batch_start + 100]
                # Extract numeric IDs from resource names if needed
                numeric_ids = []
                for cid in batch:
                    # Handle both "geoTargetConstants/12345" and plain "12345"
                    if "/" in cid:
                        numeric_ids.append(cid.split("/")[-1])
                    else:
                        numeric_ids.append(cid)

                id_list = ", ".join(numeric_ids)
                query = f"""
                    SELECT geo_target_constant.id,
                           geo_target_constant.name,
                           geo_target_constant.canonical_name,
                           geo_target_constant.target_type,
                           geo_target_constant.country_code
                    FROM geo_target_constant
                    WHERE geo_target_constant.id IN ({id_list})
                """
                try:
                    response = await self._run_sync(
                        ga_service.search, customer_id=self.customer_id, query=query
                    )
                    for row in response:
                        gtc = row.geo_target_constant
                        cid_str = str(gtc.id)
                        # Also map the resource name format
                        result_map[cid_str] = gtc.canonical_name or gtc.name
                        result_map[f"geoTargetConstants/{cid_str}"] = gtc.canonical_name or gtc.name
                except Exception as batch_err:
                    logger.warning("Geo criterion batch resolution failed",
                        batch_size=len(batch), error=str(batch_err))

            logger.info("Geo criterion IDs resolved",
                requested=len(unique_ids), resolved=len(result_map) // 2)
            return result_map
        except Exception as e:
            logger.warning("Geo criterion resolution failed", error=str(e))
            return {}

    def _geocode_location(self, location_name: str) -> dict:
        """Geocode a location name to lat/lng using a lookup table of major US metros."""
        MAJOR_METROS = {
            "dallas": (32.7767, -96.7970), "fort worth": (32.7555, -97.3308),
            "dfw": (32.8998, -97.0403), "houston": (29.7604, -95.3698),
            "san antonio": (29.4241, -98.4936), "austin": (30.2672, -97.7431),
            "phoenix": (33.4484, -112.0740), "los angeles": (34.0522, -118.2437),
            "chicago": (41.8781, -87.6298), "new york": (40.7128, -74.0060),
            "miami": (25.7617, -80.1918), "atlanta": (33.7490, -84.3880),
            "denver": (39.7392, -104.9903), "seattle": (47.6062, -122.3321),
            "portland": (45.5152, -122.6784), "las vegas": (36.1699, -115.1398),
            "orlando": (28.5383, -81.3792), "tampa": (27.9506, -82.4572),
            "charlotte": (35.2271, -80.8431), "nashville": (36.1627, -86.7816),
            "minneapolis": (44.9778, -93.2650), "detroit": (42.3314, -83.0458),
            "boston": (42.3601, -71.0589), "philadelphia": (39.9526, -75.1652),
            "san diego": (32.7157, -117.1611), "san francisco": (37.7749, -122.4194),
            "sacramento": (38.5816, -121.4944), "indianapolis": (39.7684, -86.1581),
            "columbus": (39.9612, -82.9988), "jacksonville": (30.3322, -81.6557),
            "memphis": (35.1495, -90.0490), "oklahoma city": (35.4676, -97.5164),
            "raleigh": (35.7796, -78.6382), "louisville": (38.2527, -85.7585),
            "baltimore": (39.2904, -76.6122), "milwaukee": (43.0389, -87.9065),
            "albuquerque": (35.0844, -106.6504), "tucson": (32.2226, -110.9747),
            "kansas city": (39.0997, -94.5786), "st louis": (38.6270, -90.1994),
            "pittsburgh": (40.4406, -79.9959), "cincinnati": (39.1031, -84.5120),
            "cleveland": (41.4993, -81.6944), "new orleans": (29.9511, -90.0715),
            "arlington": (32.7357, -97.1081), "plano": (33.0198, -96.6989),
            "irving": (32.8140, -96.9489), "mckinney": (33.1972, -96.6397),
            "frisco": (33.1507, -96.8236), "garland": (32.9126, -96.6389),
        }

        name_lower = location_name.lower().strip()
        for key, (lat, lng) in MAJOR_METROS.items():
            if key in name_lower:
                return {"latitude": lat, "longitude": lng, "source": "lookup"}
        return {}

    async def _apply_targeting_settings(
        self, campaign_id: str, spec: Dict, results: Dict
    ) -> None:
        """
        Apply targeting settings generated by the pipeline's Targeting Agent.
        Runs AFTER atomic deploy — these are separate API calls:
        - Location/proximity targeting (geo)
        - Device bid modifiers (mobile/tablet/desktop)
        - Ad scheduling (peak hours with bid adjustments)
        - Call extension (phone number asset)
        """
        targeting = spec.get("_pipeline_metadata", {}).get("targeting", {})
        if not targeting:
            return

        targeting_applied = []

        # ── 1. GEO TARGETING ─────────────────────────────────────────
        geo = targeting.get("geo", {})
        geo_type = geo.get("type", "radius")

        # ── Resolve missing geo data before applying ──
        try:
            if geo_type == "radius" and not geo.get("latitude"):
                # Try to geocode from location names
                locations = geo.get("locations", []) or targeting.get("locations", [])
                if locations:
                    coords = self._geocode_location(locations[0])
                    if coords:
                        geo["latitude"] = coords["latitude"]
                        geo["longitude"] = coords["longitude"]
                        logger.info("Geocoded location for radius targeting",
                            location=locations[0], lat=coords["latitude"], lng=coords["longitude"])

            elif geo_type == "cities" and not geo.get("location_ids"):
                # Resolve city names to Google Ads criterion IDs
                locations = geo.get("locations", [])
                if locations:
                    resolved = await self._resolve_geo_locations(locations)
                    if resolved:
                        geo["location_ids"] = [r["criterion_id"] for r in resolved]
                        logger.info("Resolved geo locations",
                            count=len(resolved),
                            locations=[r["name"] for r in resolved])
        except Exception as e:
            logger.warning("Geo resolution failed — will try raw targeting", error=str(e))

        try:
            if geo_type == "radius" and geo.get("radius_miles"):
                # Use proximity targeting with business coordinates
                lat = geo.get("latitude")
                lng = geo.get("longitude")
                radius = geo.get("radius_miles", 40)

                if lat and lng:
                    result = await self.add_proximity_targeting(
                        campaign_id, lat, lng, radius
                    )
                    if result.get("status") != "error":
                        targeting_applied.append(f"Proximity: {radius}mi radius")
                    else:
                        results["errors"].append(f"Geo targeting: {result.get('error', 'unknown')}")

            elif geo_type == "cities" and geo.get("location_ids"):
                for loc_id in geo["location_ids"]:
                    result = await self.add_location_targeting(campaign_id, str(loc_id))
                    if result.get("status") == "error":
                        results["errors"].append(f"Location {loc_id}: {result.get('error', '')}")
                targeting_applied.append(f"Cities: {len(geo.get('location_ids', []))} locations")

        except Exception as e:
            logger.warning("Geo targeting failed — campaign will use default targeting", error=str(e))
            results["errors"].append(f"Geo targeting: {str(e)[:100]}")

        # ── 2. DEVICE BID MODIFIERS ──────────────────────────────────
        device_bids = targeting.get("device_bids", {})
        try:
            for device_key, bid_field in [
                ("MOBILE", "mobile_bid_adj"),
                ("DESKTOP", "desktop_bid_adj"),
                ("TABLET", "tablet_bid_adj"),
            ]:
                adj_pct = device_bids.get(bid_field, 0)
                if adj_pct != 0:
                    # Convert percentage to multiplier: +30% → 1.3, -20% → 0.8
                    multiplier = 1.0 + (adj_pct / 100.0)
                    multiplier = max(0.1, min(5.0, multiplier))  # Google Ads limits
                    result = await self.set_device_bid_modifier(
                        campaign_id, device_key, multiplier
                    )
                    if result.get("status") != "error":
                        targeting_applied.append(f"{device_key}: {adj_pct:+d}%")
                    else:
                        results["errors"].append(f"Device bid {device_key}: {result.get('error', '')}")
        except Exception as e:
            logger.warning("Device bid modifiers failed", error=str(e))

        # ── 3. AD SCHEDULING ─────────────────────────────────────────
        schedule = targeting.get("schedule", {})
        peak_adjustments = schedule.get("peak_adjustments", [])
        try:
            for peak in peak_adjustments:
                days = peak.get("days", [])
                hours = peak.get("hours", "")
                bid_adj = peak.get("bid_adj", 0)

                if not hours or not days:
                    continue

                # Parse hours string like "8-20"
                parts = str(hours).split("-")
                if len(parts) != 2:
                    continue
                try:
                    start_h = int(parts[0])
                    end_h = int(parts[1])
                except ValueError:
                    continue

                multiplier = 1.0 + (bid_adj / 100.0) if bid_adj else 1.0
                multiplier = max(0.1, min(5.0, multiplier))

                for day in days:
                    result = await self.set_ad_schedule(
                        campaign_id, day.upper(), start_h, end_h, multiplier
                    )
                    if result.get("status") == "error":
                        results["errors"].append(f"Schedule {day}: {result.get('error', '')}")

                targeting_applied.append(
                    f"Schedule: {','.join(d[:3] for d in days)} {hours} ({bid_adj:+d}%)"
                )
        except Exception as e:
            logger.warning("Ad scheduling failed", error=str(e))

        # ── 4. CALL EXTENSION ────────────────────────────────────────
        call_ext = spec.get("_pipeline_metadata", {}).get("extensions", {}).get("call_extension", {})
        if not call_ext:
            # Also check top-level extensions from pipeline
            call_ext = spec.get("call_extension", {})
        phone = call_ext.get("phone", "")
        if phone:
            try:
                await self._deploy_call_extension(campaign_id, phone, call_ext.get("country_code", "US"))
                targeting_applied.append(f"Call ext: {phone}")
            except Exception as e:
                logger.warning("Call extension failed", error=str(e))
                results["errors"].append(f"Call extension: {str(e)[:100]}")

        if targeting_applied:
            results["targeting_applied"] = targeting_applied
            logger.info("Targeting settings applied",
                campaign_id=campaign_id, settings=targeting_applied)

    async def _deploy_call_extension(
        self, campaign_id: str, phone_number: str, country_code: str = "US"
    ) -> Dict[str, Any]:
        """Create a call extension asset and link it to the campaign."""
        await self._ensure_token()
        client = self._get_client()
        asset_service = client.get_service("AssetService")
        ca_service = client.get_service("CampaignAssetService")
        campaign_resource = f"customers/{self.customer_id}/campaigns/{campaign_id}"

        # Create call asset
        asset_op = client.get_type("AssetOperation")
        asset_op.create.call_asset.phone_number = phone_number
        asset_op.create.call_asset.country_code = country_code

        asset_response = await self._run_sync(
            asset_service.mutate_assets,
            customer_id=self.customer_id,
            operations=[asset_op],
        )

        if not asset_response.results:
            return {"status": "error", "error": "No asset created"}

        asset_resource = asset_response.results[0].resource_name

        # Link to campaign
        link_op = client.get_type("CampaignAssetOperation")
        link = link_op.create
        link.campaign = campaign_resource
        link.asset = asset_resource
        link.field_type = client.enums.AssetFieldTypeEnum.CALL

        await self._run_sync(
            ca_service.mutate_campaign_assets,
            customer_id=self.customer_id,
            operations=[link_op],
        )

        logger.info("Call extension deployed", campaign_id=campaign_id, phone=phone_number)
        return {"status": "created", "phone": phone_number}

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

            field_mask = field_mask_pb2.FieldMask(paths=["status"])
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

            field_mask = field_mask_pb2.FieldMask(paths=["amount_micros"])
            operation.update_mask.CopyFrom(field_mask)

            budget_service.mutate_campaign_budgets(
                customer_id=self.customer_id, operations=[operation]
            )
            return {"status": "updated", "new_amount_micros": new_amount_micros}
        except Exception as e:
            logger.error("Failed to update budget", error=str(e))
            return {"status": "error", "error": str(e)}

    # ── EXPERIMENT SERVICE ─────────────────────────────────────────

    async def create_experiment(self, name: str, campaign_id: str,
                                 suffix: str = "experiment",
                                 traffic_split_pct: int = 50) -> Dict[str, Any]:
        """Create a Google Ads experiment (campaign draft → experiment)."""
        try:
            client = self._get_client()
            campaign_resource = f"customers/{self.customer_id}/campaigns/{campaign_id}"

            # Step 1: Create campaign draft
            draft_service = client.get_service("CampaignDraftService")
            draft_op = client.get_type("CampaignDraftOperation")
            draft = draft_op.create
            draft.base_campaign = campaign_resource
            draft.name = f"{name} Draft"

            draft_response = draft_service.mutate_campaign_drafts(
                customer_id=self.customer_id, operations=[draft_op]
            )
            draft_resource = draft_response.results[0].resource_name

            # Step 2: Create experiment from draft
            experiment_service = client.get_service("ExperimentService")
            exp_op = client.get_type("ExperimentOperation")
            exp = exp_op.create
            exp.name = name
            exp.description = f"Auto-created experiment for campaign {campaign_id}"
            exp.suffix = suffix
            exp.type_ = client.enums.ExperimentTypeEnum.SEARCH_CUSTOM

            # Add experiment arm
            arm = client.get_type("ExperimentArm")
            arm.campaign = campaign_resource
            arm.control = True
            arm.traffic_split = 100 - traffic_split_pct

            exp_response = experiment_service.mutate_experiments(
                customer_id=self.customer_id, operations=[exp_op]
            )
            experiment_resource = exp_response.results[0].resource_name

            return {
                "status": "created",
                "experiment_resource": experiment_resource,
                "draft_resource": draft_resource,
            }
        except Exception as e:
            logger.error("Failed to create experiment", error=str(e))
            return {"status": "error", "error": str(e)}

    async def schedule_experiment(self, experiment_resource: str) -> Dict[str, Any]:
        """Schedule (start) a Google Ads experiment."""
        try:
            client = self._get_client()
            experiment_service = client.get_service("ExperimentService")
            experiment_service.schedule_experiment(resource_name=experiment_resource)
            return {"status": "scheduled", "resource": experiment_resource}
        except Exception as e:
            logger.error("Failed to schedule experiment", error=str(e))
            return {"status": "error", "error": str(e)}

    async def get_experiment_results(self, experiment_resource: str) -> Dict[str, Any]:
        """Fetch experiment performance metrics using GAQL."""
        try:
            client = self._get_client()
            ga_service = client.get_service("GoogleAdsService")

            # Get experiment details
            exp_id = experiment_resource.split("/")[-1]
            query = f"""
                SELECT experiment.id, experiment.name, experiment.status,
                       experiment.start_date, experiment.end_date,
                       experiment.description
                FROM experiment
                WHERE experiment.id = {exp_id}
            """
            response = ga_service.search(customer_id=self.customer_id, query=query)
            exp_data = {}
            for row in response:
                exp_data = {
                    "id": str(row.experiment.id),
                    "name": row.experiment.name,
                    "status": row.experiment.status.name if hasattr(row.experiment.status, 'name') else str(row.experiment.status),
                    "start_date": row.experiment.start_date,
                    "end_date": row.experiment.end_date,
                }

            # Get experiment arm metrics
            arms_query = f"""
                SELECT experiment_arm.experiment, experiment_arm.name,
                       experiment_arm.control, experiment_arm.traffic_split,
                       experiment_arm.campaigns,
                       metrics.impressions, metrics.clicks, metrics.cost_micros,
                       metrics.conversions, metrics.conversions_value, metrics.ctr
                FROM experiment_arm
                WHERE experiment_arm.experiment = '{experiment_resource}'
            """
            arm_results = []
            try:
                arms_response = ga_service.search(customer_id=self.customer_id, query=arms_query)
                for row in arms_response:
                    arm = row.experiment_arm
                    m = row.metrics
                    arm_results.append({
                        "name": arm.name,
                        "control": arm.control,
                        "traffic_split": arm.traffic_split,
                        "impressions": m.impressions,
                        "clicks": m.clicks,
                        "cost_micros": m.cost_micros,
                        "conversions": round(m.conversions, 2),
                        "conversion_value": round(m.conversions_value, 2),
                        "ctr": round(m.ctr, 4),
                    })
            except Exception:
                pass

            return {"status": "ok", "experiment": exp_data, "arms": arm_results}
        except Exception as e:
            logger.error("Failed to get experiment results", error=str(e))
            return {"status": "error", "error": str(e)}

    async def promote_experiment(self, experiment_resource: str) -> Dict[str, Any]:
        """Promote the winning experiment arm to the base campaign."""
        try:
            client = self._get_client()
            experiment_service = client.get_service("ExperimentService")
            experiment_service.promote_experiment(resource_name=experiment_resource)
            return {"status": "promoted", "resource": experiment_resource}
        except Exception as e:
            logger.error("Failed to promote experiment", error=str(e))
            return {"status": "error", "error": str(e)}

    async def end_experiment(self, experiment_resource: str) -> Dict[str, Any]:
        """End an experiment without promoting."""
        try:
            client = self._get_client()
            experiment_service = client.get_service("ExperimentService")
            experiment_service.end_experiment(resource_name=experiment_resource)
            return {"status": "ended", "resource": experiment_resource}
        except Exception as e:
            logger.error("Failed to end experiment", error=str(e))
            return {"status": "error", "error": str(e)}

    # ── LOCAL SERVICES ADS (LSA) ─────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_lsa_leads(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch Local Services Ads leads via GAQL.
        Returns lead details including type, status, contact info, charge status.
        """
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT local_services_lead.id,
                   local_services_lead.resource_name,
                   local_services_lead.lead_type,
                   local_services_lead.category_id,
                   local_services_lead.service_id,
                   local_services_lead.contact_details,
                   local_services_lead.lead_status,
                   local_services_lead.creation_date_time,
                   local_services_lead.locale,
                   local_services_lead.lead_charged,
                   local_services_lead.credit_details.credit_state,
                   local_services_lead.credit_details.credit_state_last_update_date_time
            FROM local_services_lead
            WHERE local_services_lead.creation_date_time DURING LAST_{days}_DAYS
            ORDER BY local_services_lead.creation_date_time DESC
            LIMIT 1000
        """
        try:
            response = ga_service.search(customer_id=self.customer_id, query=query)
        except Exception as e:
            err_str = str(e)
            if "UNRECOGNIZED" in err_str or "not found" in err_str.lower():
                logger.info("No LSA campaigns found for this account", customer_id=self.customer_id)
                return []
            raise

        results = []
        for row in response:
            lead = row.local_services_lead
            # Extract contact details
            contact_name = ""
            contact_phone = ""
            contact_email = ""
            try:
                cd = lead.contact_details
                contact_name = getattr(cd, "consumer_name", "") or ""
                contact_phone = getattr(cd, "phone_number", "") or ""
                contact_email = getattr(cd, "email", "") or ""
            except Exception:
                pass

            # Parse credit details
            credit_state = ""
            credit_state_updated = None
            try:
                credit_state = lead.credit_details.credit_state.name if lead.credit_details.credit_state else ""
                credit_state_updated = lead.credit_details.credit_state_last_update_date_time or None
            except Exception:
                pass

            results.append({
                "lead_id": str(lead.id),
                "resource_name": lead.resource_name,
                "lead_type": lead.lead_type.name if hasattr(lead.lead_type, 'name') else str(lead.lead_type),
                "category_id": str(lead.category_id) if lead.category_id else None,
                "service_id": str(lead.service_id) if lead.service_id else None,
                "lead_status": lead.lead_status.name if hasattr(lead.lead_status, 'name') else str(lead.lead_status),
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "contact_email": contact_email,
                "locale": lead.locale or None,
                "lead_charged": bool(lead.lead_charged),
                "credit_state": credit_state,
                "credit_state_updated": credit_state_updated,
                "creation_date_time": lead.creation_date_time,
            })
        logger.info("Fetched LSA leads", customer_id=self.customer_id, count=len(results))
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_lsa_conversations(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch LSA lead conversations (call recordings, messages) via GAQL.
        """
        client = self._get_client()
        ga_service = client.get_service("GoogleAdsService")
        query = f"""
            SELECT local_services_lead_conversation.id,
                   local_services_lead_conversation.resource_name,
                   local_services_lead_conversation.conversation_channel,
                   local_services_lead_conversation.participant_type,
                   local_services_lead_conversation.lead,
                   local_services_lead_conversation.event_date_time,
                   local_services_lead_conversation.phone_call_details.call_duration_millis,
                   local_services_lead_conversation.phone_call_details.call_recording_url,
                   local_services_lead_conversation.message_details.text,
                   local_services_lead_conversation.message_details.attachment_urls
            FROM local_services_lead_conversation
            WHERE local_services_lead_conversation.event_date_time DURING LAST_{days}_DAYS
            ORDER BY local_services_lead_conversation.event_date_time DESC
            LIMIT 2000
        """
        try:
            response = ga_service.search(customer_id=self.customer_id, query=query)
        except Exception as e:
            err_str = str(e)
            if "UNRECOGNIZED" in err_str or "not found" in err_str.lower():
                logger.info("No LSA conversations found", customer_id=self.customer_id)
                return []
            raise

        results = []
        for row in response:
            conv = row.local_services_lead_conversation
            # Phone call details
            call_duration_ms = None
            call_recording_url = None
            try:
                pcd = conv.phone_call_details
                call_duration_ms = pcd.call_duration_millis if pcd.call_duration_millis else None
                call_recording_url = pcd.call_recording_url if pcd.call_recording_url else None
            except Exception:
                pass

            # Message details
            message_text = None
            attachment_urls = None
            try:
                md = conv.message_details
                message_text = md.text if md.text else None
                attachment_urls = list(md.attachment_urls) if md.attachment_urls else None
            except Exception:
                pass

            # Extract lead resource name from the lead reference
            lead_resource = ""
            try:
                lead_resource = conv.lead or ""
            except Exception:
                pass

            results.append({
                "conversation_id": str(conv.id),
                "resource_name": conv.resource_name,
                "channel": conv.conversation_channel.name if hasattr(conv.conversation_channel, 'name') else str(conv.conversation_channel),
                "participant_type": conv.participant_type.name if hasattr(conv.participant_type, 'name') else str(conv.participant_type),
                "lead_resource_name": lead_resource,
                "event_date_time": conv.event_date_time,
                "call_duration_ms": call_duration_ms,
                "call_recording_url": call_recording_url,
                "message_text": message_text,
                "attachment_urls": attachment_urls,
            })
        logger.info("Fetched LSA conversations", customer_id=self.customer_id, count=len(results))
        return results

    async def submit_lsa_lead_feedback(self, lead_resource_name: str, feedback_type: str = "DISPUTE") -> Dict[str, Any]:
        """
        Submit feedback on an LSA lead (e.g., dispute a bad lead).
        feedback_type: "DISPUTE" to request credit for a bad lead.
        """
        try:
            client = self._get_client()
            lsa_service = client.get_service("LocalServicesLeadService")

            # Build the feedback request
            request = client.get_type("ProvideLocalServicesLeadRequest")
            request.resource_name = lead_resource_name

            if feedback_type == "DISPUTE":
                request.lead_feedback_submissions.append(
                    client.get_type("LocalServicesLeadFeedbackSubmission")
                )

            response = lsa_service.provide_local_services_lead(request=request)
            logger.info("LSA lead feedback submitted", lead=lead_resource_name, type=feedback_type)
            return {"status": "submitted", "resource": lead_resource_name}
        except Exception as e:
            logger.error("Failed to submit LSA lead feedback", lead=lead_resource_name, error=str(e))
            return {"status": "error", "error": str(e)}
