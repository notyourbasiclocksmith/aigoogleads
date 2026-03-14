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
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

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
            expires_in = tokens.get("expires_in", 3500)
            from datetime import timedelta
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 60)
        else:
            raise Exception("Failed to refresh Google Ads access token — Google returned non-200. Check client_id/secret and refresh_token.")

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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
    async def get_auction_insights(self, campaign_id: str) -> List[Dict[str, Any]]:
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
                   recommendation.sitelink_extension_recommendation,
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
                customer_id=self.customer_id, operations=operations
            )
            return {"status": "created", "count": len(response.results)}
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

            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("cpc_bid_micros")
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

            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("status")
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

            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("status")
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

            field_mask = client.get_type("FieldMask")
            field_mask.paths.append("status")
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
            campaign_bid_modifier_service = client.get_service("CampaignBidModifierService")

            operation = client.get_type("CampaignBidModifierOperation")
            modifier = operation.create
            modifier.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
            modifier.bid_modifier = bid_modifier

            device_map = {
                "MOBILE": client.enums.DeviceEnum.MOBILE,
                "TABLET": client.enums.DeviceEnum.TABLET,
                "DESKTOP": client.enums.DeviceEnum.DESKTOP,
            }
            modifier.device.type_ = device_map.get(device.upper(), client.enums.DeviceEnum.MOBILE)

            campaign_bid_modifier_service.mutate_campaign_bid_modifiers(
                customer_id=self.customer_id, operations=[operation]
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

            campaign_criterion_service.mutate_campaign_criteria(
                customer_id=self.customer_id, operations=[operation]
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

            campaign_criterion_service.mutate_campaign_criteria(
                customer_id=self.customer_id, operations=[operation]
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

            campaign_criterion_service.mutate_campaign_criteria(
                customer_id=self.customer_id, operations=[operation]
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

            # Channel type
            channel = campaign_data.get("channel_type", "SEARCH").upper()
            channel_map = {
                "SEARCH": client.enums.AdvertisingChannelTypeEnum.SEARCH,
                "DISPLAY": client.enums.AdvertisingChannelTypeEnum.DISPLAY,
                "PERFORMANCE_MAX": client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX,
            }
            campaign.advertising_channel_type = channel_map.get(
                channel, client.enums.AdvertisingChannelTypeEnum.SEARCH
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
            if ad_data.get("final_urls"):
                ag_ad.ad.final_urls.extend(ad_data["final_urls"])

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

            # Headlines (≤30 chars, up to 5)
            for headline in text_assets.get("headlines", [])[:5]:
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
