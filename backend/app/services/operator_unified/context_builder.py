"""
Unified Context Builder — assembles normalized context from multiple systems.

Pulls real data from Google Ads, Meta Ads, GBP, and Image services.
Handles partial failures gracefully — never fails the whole request
if one connector is unavailable.
"""
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class UnifiedContextBuilder:
    """Builds a single normalized context object from all connected systems."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def build(
        self,
        systems: List[str],
        customer_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> Dict[str, Any]:
        """
        Build context for requested systems.
        Returns partial context if some systems fail.
        """
        context: Dict[str, Any] = {
            "mode": "unified",
            "connected_systems": [],
            "system_errors": {},
        }

        for system in systems:
            try:
                if system == "google_ads":
                    ctx = await self._build_google_ads_context(customer_id, date_range)
                    context["google_ads"] = ctx
                    context["connected_systems"].append("google_ads")
                elif system == "meta_ads":
                    ctx = await self._build_meta_ads_context()
                    context["meta_ads"] = ctx
                    context["connected_systems"].append("meta_ads")
                elif system == "gbp":
                    ctx = await self._build_gbp_context()
                    context["gbp"] = ctx
                    context["connected_systems"].append("gbp")
                elif system == "image":
                    ctx = await self._build_image_context()
                    context["image"] = ctx
                    context["connected_systems"].append("image")
            except Exception as e:
                error_msg = str(e)[:200]
                logger.warning("context_builder_system_failed", system=system, error=error_msg)
                context["system_errors"][system] = error_msg

        return context

    async def _build_google_ads_context(
        self, customer_id: Optional[str], date_range: str,
    ) -> Dict[str, Any]:
        """Pull Google Ads context using existing operator context service."""
        from app.models.integration_google_ads import IntegrationGoogleAds
        from app.integrations.google_ads.client import GoogleAdsClient
        from app.services.operator.context_service import GoogleAdsContextService
        from sqlalchemy import select, and_

        # Find active integration
        stmt = select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == self.tenant_id,
            IntegrationGoogleAds.is_active == True,
        )
        if customer_id:
            stmt = stmt.where(IntegrationGoogleAds.customer_id == customer_id)
        result = await self.db.execute(stmt)
        integration = result.scalars().first()
        if not integration:
            return {"connected": False, "error": "No active Google Ads integration"}

        ads_client = GoogleAdsClient(
            customer_id=integration.customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
        )
        context_svc = GoogleAdsContextService(ads_client)
        raw = await context_svc.build_full_context(date_range)

        return {
            "connected": True,
            "customer_id": integration.customer_id,
            "account": raw.get("account", {}),
            "campaign_performance": raw.get("campaign_performance", []),
            "keyword_performance": raw.get("keyword_performance", [])[:50],
            "search_terms": raw.get("search_terms", [])[:40],
            "ad_performance": raw.get("ad_performance", [])[:20],
            "heuristics": raw.get("heuristics", {}),
        }

    async def _build_meta_ads_context(self) -> Dict[str, Any]:
        """Pull Meta Ads context using existing meta service."""
        from app.services.meta_service import MetaService

        svc = MetaService(self.db)
        try:
            raw = await svc.build_full_context(self.tenant_id)
        except ValueError:
            return {"connected": False, "error": "No Meta Ads integration configured"}

        return {
            "connected": True,
            "ad_account_id": raw.get("account", {}).get("account_id"),
            "account": raw.get("account", {}),
            "campaigns": raw.get("campaigns", []),
            "performance": raw.get("performance", []),
            "audiences": raw.get("audiences", []),
            "heuristics": raw.get("heuristics", {}),
        }

    async def _build_gbp_context(self) -> Dict[str, Any]:
        """Pull GBP context using existing GBP service."""
        from app.services.gbp_service import GBPService

        svc = GBPService(self.db)
        try:
            business_info = await svc.get_business_info(self.tenant_id)
        except ValueError:
            return {"connected": False, "error": "No GBP integration configured"}

        reviews = {}
        posts = {}
        try:
            reviews = await svc.get_reviews(self.tenant_id, page_size=20)
        except Exception as e:
            logger.warning("gbp_reviews_failed", error=str(e)[:100])

        try:
            posts = await svc.get_posts(self.tenant_id)
        except Exception as e:
            logger.warning("gbp_posts_failed", error=str(e)[:100])

        return {
            "connected": True,
            "business_info": business_info,
            "reviews": reviews.get("reviews", []),
            "review_summary": {
                "total": reviews.get("total_review_count", 0),
                "average_rating": reviews.get("average_rating", 0),
                "unanswered": sum(1 for r in reviews.get("reviews", []) if not r.get("reply")),
            },
            "posts": posts.get("posts", []),
        }

    async def _build_image_context(self) -> Dict[str, Any]:
        """Check image generation availability."""
        from app.integrations.image_generator.client import ImageGeneratorClient

        client = ImageGeneratorClient()
        return {
            "available": client.is_configured,
            "capabilities": ["generate", "generate_ad", "generate_social"],
            "engines": ["dalle", "stability", "flux"],
        }
