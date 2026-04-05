"""
Brain Service — bridges Jarvis connector calls to Google Ads API reads/writes.

Maps every /api/v1/brain/* endpoint to the underlying GoogleAdsClient + ContextService.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.integration_google_ads import IntegrationGoogleAds
from app.integrations.google_ads.client import GoogleAdsClient
from app.services.operator.context_service import GoogleAdsContextService
from app.core.security import decrypt_token

logger = structlog.get_logger()


class BrainService:
    """Wraps GoogleAdsClient + ContextService for Jarvis brain API calls."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_ads_client(self, tenant_id: str, customer_id: Optional[str] = None) -> GoogleAdsClient:
        """Get an authenticated Google Ads client for a tenant."""
        query = select(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.tenant_id == tenant_id,
                IntegrationGoogleAds.is_active == True,
            )
        )
        if customer_id:
            query = query.where(IntegrationGoogleAds.customer_id == customer_id)
        result = await self.db.execute(query)
        integration = result.scalars().first()
        if not integration:
            raise ValueError("No active Google Ads integration found")
        return GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
        )

    def _resolve_date_range(
        self, date_from: Optional[str], date_to: Optional[str]
    ) -> str:
        """Convert date_from/date_to to a GAQL date range string."""
        if not date_from:
            return "LAST_30_DAYS"
        # If both provided, we use custom date range in GAQL WHERE clause
        return "CUSTOM"

    def _date_where_clause(
        self, date_from: Optional[str], date_to: Optional[str]
    ) -> str:
        """Build GAQL WHERE clause for date filtering."""
        if not date_from:
            return "segments.date DURING LAST_30_DAYS"
        if date_to:
            return f"segments.date BETWEEN '{date_from}' AND '{date_to}'"
        return f"segments.date >= '{date_from}'"

    # ── Health ──────────────────────────────────────────────────

    async def health_check(self, tenant_id: str) -> Dict[str, Any]:
        try:
            client = await self._get_ads_client(tenant_id)
            info = await client.get_account_info()
            return {"status": "healthy", "account": info}
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    # ── Campaign Performance ────────────────────────────────────

    async def get_campaign_performance(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None, campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        ctx = GoogleAdsContextService(client)
        date_range = self._resolve_date_range(date_from, date_to)
        if date_range == "CUSTOM":
            # Use custom GAQL
            return await self._custom_campaign_performance(client, date_from, date_to, campaign_id)
        perf = await ctx._get_campaign_performance(date_range)
        if campaign_id:
            perf = [c for c in perf if c["campaign_id"] == campaign_id]
        return {"campaigns": perf, "count": len(perf)}

    async def _custom_campaign_performance(
        self, client: GoogleAdsClient, date_from: str, date_to: Optional[str],
        campaign_id: Optional[str],
    ) -> Dict[str, Any]:
        """Campaign performance with custom date range."""
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = self._date_where_clause(date_from, date_to)
            if campaign_id:
                where += f" AND campaign.id = {campaign_id}"
            query = f"""
                SELECT campaign.id, campaign.name, campaign.status,
                       campaign_budget.amount_micros,
                       metrics.impressions, metrics.clicks, metrics.cost_micros,
                       metrics.conversions, metrics.conversions_value,
                       metrics.ctr, metrics.average_cpc, metrics.cost_per_conversion
                FROM campaign
                WHERE campaign.status != 'REMOVED' AND {where}
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            agg = {}
            for row in response:
                cid = str(row.campaign.id)
                if cid not in agg:
                    agg[cid] = {
                        "campaign_id": cid, "name": row.campaign.name,
                        "status": row.campaign.status.name,
                        "daily_budget": round(row.campaign_budget.amount_micros / 1_000_000, 2),
                        "impressions": 0, "clicks": 0, "cost": 0,
                        "conversions": 0, "conv_value": 0,
                    }
                agg[cid]["impressions"] += row.metrics.impressions
                agg[cid]["clicks"] += row.metrics.clicks
                agg[cid]["cost"] += row.metrics.cost_micros / 1_000_000
                agg[cid]["conversions"] += row.metrics.conversions
                agg[cid]["conv_value"] += row.metrics.conversions_value
            for c in agg.values():
                c["cost"] = round(c["cost"], 2)
                c["ctr"] = round(c["clicks"] / c["impressions"] * 100, 2) if c["impressions"] > 0 else 0
                c["cost_per_conversion"] = round(c["cost"] / c["conversions"], 2) if c["conversions"] > 0 else 0
            result = sorted(agg.values(), key=lambda x: x["cost"], reverse=True)
            return {"campaigns": result, "count": len(result)}
        except Exception as e:
            logger.error("Custom campaign performance failed", error=str(e))
            return {"campaigns": [], "count": 0, "error": str(e)[:200]}

    # ── Campaign List ───────────────────────────────────────────

    async def get_campaigns(self, tenant_id: str, status: Optional[str] = None) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        campaigns = await client.get_campaigns()
        if status:
            campaigns = [c for c in campaigns if c["status"] == status.upper()]
        return {"campaigns": campaigns, "count": len(campaigns)}

    # ── Campaign ROI ────────────────────────────────────────────

    async def get_campaign_roi(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = await self.get_campaign_performance(tenant_id, date_from, date_to)
        campaigns = result.get("campaigns", [])
        for c in campaigns:
            c["roas"] = round(c["conv_value"] / c["cost"], 2) if c.get("cost", 0) > 0 else 0
        total_cost = sum(c.get("cost", 0) for c in campaigns)
        total_value = sum(c.get("conv_value", 0) for c in campaigns)
        return {
            "campaigns": campaigns,
            "totals": {
                "cost": round(total_cost, 2),
                "conv_value": round(total_value, 2),
                "roas": round(total_value / total_cost, 2) if total_cost > 0 else 0,
            },
        }

    # ── Ad Group Performance ────────────────────────────────────

    async def get_adgroup_performance(
        self, tenant_id: str, campaign_id: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = self._date_where_clause(date_from, date_to)
            if campaign_id:
                where += f" AND campaign.id = {campaign_id}"
            query = f"""
                SELECT campaign.id, campaign.name,
                       ad_group.id, ad_group.name, ad_group.status,
                       metrics.impressions, metrics.clicks, metrics.cost_micros,
                       metrics.conversions, metrics.ctr, metrics.average_cpc
                FROM ad_group
                WHERE ad_group.status != 'REMOVED' AND {where}
                ORDER BY metrics.cost_micros DESC
                LIMIT 100
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            ad_groups = []
            for row in response:
                ad_groups.append({
                    "ad_group_id": str(row.ad_group.id),
                    "name": row.ad_group.name,
                    "status": row.ad_group.status.name,
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                    "conversions": row.metrics.conversions,
                    "ctr": round(row.metrics.ctr * 100, 2),
                    "avg_cpc": round(row.metrics.average_cpc / 1_000_000, 2),
                })
            return {"ad_groups": ad_groups, "count": len(ad_groups)}
        except Exception as e:
            logger.error("Ad group perf failed", error=str(e))
            return {"ad_groups": [], "count": 0, "error": str(e)[:200]}

    # ── Keyword Performance ─────────────────────────────────────

    async def get_keyword_performance(
        self, tenant_id: str, campaign_id: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        min_cost: Optional[float] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        ctx = GoogleAdsContextService(client)
        date_range = self._resolve_date_range(date_from, date_to)
        if date_range == "CUSTOM":
            keywords = await self._custom_keyword_performance(client, date_from, date_to, campaign_id)
        else:
            keywords = await ctx._get_all_keyword_performance(date_range)
        if campaign_id and date_range != "CUSTOM":
            keywords = [k for k in keywords if k["campaign_id"] == campaign_id]
        if min_cost:
            keywords = [k for k in keywords if k["cost"] >= min_cost]
        return {"keywords": keywords, "count": len(keywords)}

    async def _custom_keyword_performance(
        self, client: GoogleAdsClient, date_from: str, date_to: Optional[str],
        campaign_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = self._date_where_clause(date_from, date_to)
            if campaign_id:
                where += f" AND campaign.id = {campaign_id}"
            query = f"""
                SELECT campaign.id, campaign.name, ad_group.id, ad_group.name,
                       ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
                       ad_group_criterion.keyword.match_type, ad_group_criterion.status,
                       ad_group_criterion.quality_info.quality_score,
                       metrics.impressions, metrics.clicks, metrics.cost_micros,
                       metrics.conversions, metrics.ctr, metrics.average_cpc
                FROM keyword_view
                WHERE campaign.status != 'REMOVED' AND ad_group_criterion.status != 'REMOVED' AND {where}
                ORDER BY metrics.cost_micros DESC LIMIT 200
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            return [
                {
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
                }
                for row in response
            ]
        except Exception as e:
            logger.error("Custom keyword perf failed", error=str(e))
            return []

    # ── Keyword Quality Scores ──────────────────────────────────

    async def get_keyword_quality(
        self, tenant_id: str, campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = "ad_group_criterion.status != 'REMOVED' AND ad_group_criterion.type = 'KEYWORD'"
            if campaign_id:
                where += f" AND campaign.id = {campaign_id}"
            query = f"""
                SELECT campaign.id, campaign.name, ad_group.id,
                       ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
                       ad_group_criterion.keyword.match_type,
                       ad_group_criterion.quality_info.quality_score,
                       ad_group_criterion.quality_info.creative_quality_score,
                       ad_group_criterion.quality_info.post_click_quality_score,
                       ad_group_criterion.quality_info.search_predicted_ctr
                FROM ad_group_criterion
                WHERE {where}
                ORDER BY ad_group_criterion.quality_info.quality_score ASC
                LIMIT 200
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            keywords = []
            for row in response:
                qi = row.ad_group_criterion.quality_info
                keywords.append({
                    "keyword_id": str(row.ad_group_criterion.criterion_id),
                    "text": row.ad_group_criterion.keyword.text,
                    "match_type": row.ad_group_criterion.keyword.match_type.name,
                    "campaign_id": str(row.campaign.id),
                    "quality_score": qi.quality_score if qi.quality_score else None,
                    "creative_quality": qi.creative_quality_score.name if hasattr(qi.creative_quality_score, 'name') else None,
                    "landing_page_quality": qi.post_click_quality_score.name if hasattr(qi.post_click_quality_score, 'name') else None,
                    "expected_ctr": qi.search_predicted_ctr.name if hasattr(qi.search_predicted_ctr, 'name') else None,
                })
            return {"keywords": keywords, "count": len(keywords)}
        except Exception as e:
            logger.error("Quality scores failed", error=str(e))
            return {"keywords": [], "count": 0, "error": str(e)[:200]}

    # ── Search Terms ────────────────────────────────────────────

    async def get_search_terms(
        self, tenant_id: str, campaign_id: Optional[str] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        ctx = GoogleAdsContextService(client)
        date_range = self._resolve_date_range(date_from, date_to)
        terms = await ctx._get_search_term_report(date_range if date_range != "CUSTOM" else "LAST_30_DAYS")
        if campaign_id:
            terms = [t for t in terms if t["campaign_id"] == campaign_id]
        return {"search_terms": terms, "count": len(terms)}

    async def get_search_term_waste(
        self, tenant_id: str, date_from: Optional[str] = None,
        min_cost: float = 10.0, max_conversions: int = 0,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        ctx = GoogleAdsContextService(client)
        date_range = self._resolve_date_range(date_from, None)
        terms = await ctx._get_search_term_report(date_range if date_range != "CUSTOM" else "LAST_30_DAYS")
        wasted = [t for t in terms if t["cost"] >= min_cost and t["conversions"] <= max_conversions]
        total_waste = sum(t["cost"] for t in wasted)
        return {
            "wasted_terms": wasted,
            "count": len(wasted),
            "total_wasted_spend": round(total_waste, 2),
        }

    # ── Conversions ─────────────────────────────────────────────

    async def get_conversions(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None, conversion_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = self._date_where_clause(date_from, date_to)
            if conversion_action:
                where += f" AND conversion_action.name = '{conversion_action}'"
            query = f"""
                SELECT campaign.id, campaign.name,
                       conversion_action.id, conversion_action.name, conversion_action.category,
                       metrics.conversions, metrics.conversions_value, metrics.cost_micros
                FROM campaign
                WHERE campaign.status != 'REMOVED' AND metrics.conversions > 0 AND {where}
                ORDER BY metrics.conversions DESC
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            conversions = []
            for row in response:
                conversions.append({
                    "campaign_id": str(row.campaign.id),
                    "campaign_name": row.campaign.name,
                    "action_id": str(row.conversion_action.id),
                    "action_name": row.conversion_action.name,
                    "category": row.conversion_action.category.name,
                    "conversions": row.metrics.conversions,
                    "value": row.metrics.conversions_value,
                    "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                })
            total_conv = sum(c["conversions"] for c in conversions)
            total_value = sum(c["value"] for c in conversions)
            return {"conversions": conversions, "total_conversions": total_conv, "total_value": round(total_value, 2)}
        except Exception as e:
            logger.error("Conversions fetch failed", error=str(e))
            return {"conversions": [], "total_conversions": 0, "error": str(e)[:200]}

    async def get_call_conversions(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get call-type conversions specifically."""
        result = await self.get_conversions(tenant_id, date_from, date_to)
        call_convs = [c for c in result.get("conversions", []) if "call" in c.get("action_name", "").lower() or c.get("category") == "PHONE_CALL_LEAD"]
        return {"call_conversions": call_convs, "count": len(call_convs)}

    async def get_conversion_lag(
        self, tenant_id: str, date_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Conversion lag analysis — how long from click to conversion."""
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = self._date_where_clause(date_from, None)
            query = f"""
                SELECT campaign.id, campaign.name,
                       segments.conversion_lag_bucket,
                       metrics.conversions
                FROM campaign
                WHERE campaign.status != 'REMOVED' AND metrics.conversions > 0 AND {where}
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            lag_data = {}
            for row in response:
                bucket = row.segments.conversion_lag_bucket.name if hasattr(row.segments.conversion_lag_bucket, 'name') else str(row.segments.conversion_lag_bucket)
                lag_data[bucket] = lag_data.get(bucket, 0) + row.metrics.conversions
            return {"lag_buckets": lag_data}
        except Exception as e:
            logger.error("Conversion lag failed", error=str(e))
            return {"lag_buckets": {}, "error": str(e)[:200]}

    # ── Cost & Budget ───────────────────────────────────────────

    async def get_cost_summary(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = await self.get_campaign_performance(tenant_id, date_from, date_to)
        campaigns = result.get("campaigns", [])
        total_cost = sum(c.get("cost", 0) for c in campaigns)
        total_clicks = sum(c.get("clicks", 0) for c in campaigns)
        total_conversions = sum(c.get("conversions", 0) for c in campaigns)
        total_impressions = sum(c.get("impressions", 0) for c in campaigns)
        return {
            "total_cost": round(total_cost, 2),
            "total_clicks": total_clicks,
            "total_conversions": total_conversions,
            "total_impressions": total_impressions,
            "avg_cpc": round(total_cost / total_clicks, 2) if total_clicks > 0 else 0,
            "avg_cpa": round(total_cost / total_conversions, 2) if total_conversions > 0 else 0,
            "campaign_count": len(campaigns),
        }

    async def get_budgets(self, tenant_id: str) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        campaigns = await client.get_campaigns()
        budgets = []
        for c in campaigns:
            budgets.append({
                "campaign_id": c["campaign_id"],
                "name": c["name"],
                "status": c["status"],
                "daily_budget": round(c.get("budget_micros", 0) / 1_000_000, 2),
                "budget_micros": c.get("budget_micros", 0),
            })
        total_daily = sum(b["daily_budget"] for b in budgets if b["status"] == "ENABLED")
        return {"budgets": budgets, "total_daily_budget": round(total_daily, 2)}

    async def get_budget_recommendations(
        self, tenant_id: str, date_from: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Budget shift recommendations based on ROI."""
        perf = await self.get_campaign_performance(tenant_id, date_from)
        campaigns = perf.get("campaigns", [])
        recommendations = []
        for c in campaigns:
            conv = c.get("conversions", 0)
            cost = c.get("cost", 0)
            if conv > 0 and cost > 0:
                cpa = cost / conv
                recommendations.append({
                    "campaign_id": c["campaign_id"],
                    "name": c["name"],
                    "current_budget": c.get("daily_budget", 0),
                    "cpa": round(cpa, 2),
                    "conversions": conv,
                    "recommendation": "increase_budget" if cpa < 50 else "review",
                })
            elif cost > 50 and conv == 0:
                recommendations.append({
                    "campaign_id": c["campaign_id"],
                    "name": c["name"],
                    "current_budget": c.get("daily_budget", 0),
                    "cpa": 0,
                    "conversions": 0,
                    "recommendation": "decrease_or_pause",
                })
        return {"recommendations": recommendations}

    # ── Bid Recommendations ─────────────────────────────────────

    async def get_bid_recommendations(
        self, tenant_id: str, campaign_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        kw_result = await self.get_keyword_performance(tenant_id, campaign_id)
        keywords = kw_result.get("keywords", [])
        recommendations = []
        for k in keywords:
            if k["conversions"] > 0 and k["cost"] > 0:
                cpa = k["cost"] / k["conversions"]
                if cpa < 30:
                    recommendations.append({
                        "keyword_id": k["keyword_id"],
                        "text": k["text"],
                        "current_cpa": round(cpa, 2),
                        "recommendation": "increase_bid",
                        "reason": "Low CPA — profitable keyword",
                    })
            elif k["cost"] > 50 and k["conversions"] == 0:
                recommendations.append({
                    "keyword_id": k["keyword_id"],
                    "text": k["text"],
                    "cost": k["cost"],
                    "recommendation": "decrease_bid",
                    "reason": "High spend with zero conversions",
                })
        return {"recommendations": recommendations}

    async def get_keyword_pause_recommendations(
        self, tenant_id: str, min_spend: float = 20.0, max_conversions: int = 0,
    ) -> Dict[str, Any]:
        kw_result = await self.get_keyword_performance(tenant_id)
        keywords = kw_result.get("keywords", [])
        to_pause = [k for k in keywords if k["cost"] >= min_spend and k["conversions"] <= max_conversions]
        total_savings = sum(k["cost"] for k in to_pause)
        return {
            "keywords_to_pause": to_pause,
            "count": len(to_pause),
            "potential_savings": round(total_savings, 2),
        }

    # ── Location & Category Performance ─────────────────────────

    async def get_location_performance(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            where = self._date_where_clause(date_from, date_to)
            query = f"""
                SELECT campaign.id,
                       geographic_view.country_criterion_id,
                       geographic_view.location_type,
                       metrics.impressions, metrics.clicks, metrics.cost_micros,
                       metrics.conversions
                FROM geographic_view
                WHERE {where}
                ORDER BY metrics.cost_micros DESC
                LIMIT 50
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            locations = []
            for row in response:
                locations.append({
                    "campaign_id": str(row.campaign.id),
                    "location_id": str(row.geographic_view.country_criterion_id),
                    "location_type": row.geographic_view.location_type.name if hasattr(row.geographic_view.location_type, 'name') else str(row.geographic_view.location_type),
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                    "conversions": row.metrics.conversions,
                })
            return {"locations": locations, "count": len(locations)}
        except Exception as e:
            logger.error("Location perf failed", error=str(e))
            return {"locations": [], "count": 0, "error": str(e)[:200]}

    async def get_category_performance(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Service category performance (uses campaign naming convention)."""
        result = await self.get_campaign_performance(tenant_id, date_from, date_to)
        return {"categories": result.get("campaigns", []), "count": result.get("count", 0)}

    # ── Quality Trends ──────────────────────────────────────────

    async def get_quality_trends(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        quality = await self.get_keyword_quality(tenant_id)
        keywords = quality.get("keywords", [])
        scores = [k["quality_score"] for k in keywords if k.get("quality_score")]
        avg_qs = round(sum(scores) / len(scores), 1) if scores else 0
        distribution = {}
        for s in scores:
            distribution[str(s)] = distribution.get(str(s), 0) + 1
        return {
            "average_quality_score": avg_qs,
            "total_keywords": len(keywords),
            "keywords_with_qs": len(scores),
            "distribution": distribution,
        }

    # ── Waste Detection ─────────────────────────────────────────

    async def detect_wasted_spend(
        self, tenant_id: str, date_from: Optional[str] = None, min_spend: float = 50.0,
    ) -> Dict[str, Any]:
        kw_result = await self.get_keyword_performance(tenant_id, date_from=date_from)
        keywords = kw_result.get("keywords", [])
        st_result = await self.get_search_term_waste(tenant_id, date_from, min_cost=10)
        wasted_keywords = [k for k in keywords if k["cost"] >= min_spend and k["conversions"] == 0]
        kw_waste = sum(k["cost"] for k in wasted_keywords)
        st_waste = st_result.get("total_wasted_spend", 0)
        return {
            "wasted_keywords": wasted_keywords[:20],
            "wasted_search_terms": st_result.get("wasted_terms", [])[:20],
            "keyword_waste_total": round(kw_waste, 2),
            "search_term_waste_total": round(st_waste, 2),
            "total_waste": round(kw_waste + st_waste, 2),
        }

    # ── Lead Attribution ────────────────────────────────────────

    async def get_lead_attribution(
        self, tenant_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        conv_result = await self.get_conversions(tenant_id, date_from, date_to)
        perf_result = await self.get_campaign_performance(tenant_id, date_from, date_to)
        return {
            "conversions_by_action": conv_result.get("conversions", []),
            "campaigns": perf_result.get("campaigns", []),
            "total_conversions": conv_result.get("total_conversions", 0),
            "total_value": conv_result.get("total_value", 0),
        }

    # ── Write Actions ───────────────────────────────────────────

    async def pause_keyword(
        self, tenant_id: str, keyword_id: str, reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Pause a keyword by ID. Requires finding the right ad_group first."""
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            # Find the keyword's ad group
            query = f"""
                SELECT ad_group.id, ad_group_criterion.criterion_id, ad_group_criterion.keyword.text
                FROM ad_group_criterion
                WHERE ad_group_criterion.criterion_id = {keyword_id}
                  AND ad_group_criterion.type = 'KEYWORD'
                LIMIT 1
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            for row in response:
                agc_service = gc.get_service("AdGroupCriterionService")
                resource = f"customers/{client.customer_id}/adGroupCriteria/{row.ad_group.id}~{keyword_id}"
                operation = gc.get_type("AdGroupCriterionOperation")
                criterion = operation.update
                criterion.resource_name = resource
                criterion.status = gc.enums.AdGroupCriterionStatusEnum.PAUSED
                field_mask = gc.get_type("FieldMask")
                field_mask.paths.append("status")
                operation.update_mask.CopyFrom(field_mask)
                agc_service.mutate_ad_group_criteria(customer_id=client.customer_id, operations=[operation])
                return {"status": "paused", "keyword_id": keyword_id, "text": row.ad_group_criterion.keyword.text}
            return {"status": "error", "error": f"Keyword {keyword_id} not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    async def update_keyword_bid(
        self, tenant_id: str, keyword_id: str, new_bid_micros: int, reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            query = f"""
                SELECT ad_group.id, ad_group_criterion.criterion_id,
                       ad_group_criterion.effective_cpc_bid_micros
                FROM ad_group_criterion
                WHERE ad_group_criterion.criterion_id = {keyword_id}
                  AND ad_group_criterion.type = 'KEYWORD'
                LIMIT 1
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            for row in response:
                before_bid = row.ad_group_criterion.effective_cpc_bid_micros
                resource = f"customers/{client.customer_id}/adGroupCriteria/{row.ad_group.id}~{keyword_id}"
                agc_service = gc.get_service("AdGroupCriterionService")
                operation = gc.get_type("AdGroupCriterionOperation")
                criterion = operation.update
                criterion.resource_name = resource
                criterion.cpc_bid_micros = new_bid_micros
                field_mask = gc.get_type("FieldMask")
                field_mask.paths.append("cpc_bid_micros")
                operation.update_mask.CopyFrom(field_mask)
                agc_service.mutate_ad_group_criteria(customer_id=client.customer_id, operations=[operation])
                return {"status": "updated", "keyword_id": keyword_id, "before_bid_micros": before_bid, "after_bid_micros": new_bid_micros}
            return {"status": "error", "error": f"Keyword {keyword_id} not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    async def update_campaign_budget(
        self, tenant_id: str, campaign_id: str, new_budget_micros: int, reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_ads_client(tenant_id)
        try:
            gc = client._get_client()
            ga_service = gc.get_service("GoogleAdsService")
            query = f"""
                SELECT campaign.id, campaign_budget.resource_name, campaign_budget.amount_micros
                FROM campaign
                WHERE campaign.id = {campaign_id}
                LIMIT 1
            """
            response = ga_service.search(customer_id=client.customer_id, query=query)
            for row in response:
                before = row.campaign_budget.amount_micros
                result = await client.update_campaign_budget(row.campaign_budget.resource_name, new_budget_micros)
                result["before_budget_micros"] = before
                result["campaign_id"] = campaign_id
                return result
            return {"status": "error", "error": f"Campaign {campaign_id} not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}

    # ── Operator / AI Scan ──────────────────────────────────────

    async def run_operator_scan(self, tenant_id: str) -> Dict[str, Any]:
        """Run a full AI-powered account scan."""
        client = await self._get_ads_client(tenant_id)
        ctx = GoogleAdsContextService(client)
        context = await ctx.build_full_context("LAST_30_DAYS")
        return {
            "status": "completed",
            "account": context.get("account", {}),
            "heuristics": context.get("heuristics", {}),
            "campaign_count": len(context.get("campaigns", [])),
            "keyword_count": len(context.get("keyword_performance", [])),
            "search_term_count": len(context.get("search_terms", [])),
        }
