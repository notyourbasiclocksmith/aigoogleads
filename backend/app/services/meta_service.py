"""
Meta Ads Brain Service — bridges Jarvis calls to Meta Marketing API.
Includes AI-powered campaign analysis and ad creative generation.
"""
from typing import Dict, Any, Optional, List
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.meta_ads.client import MetaAdsClient
from app.integrations.image_generator.client import ImageGeneratorClient
from app.core.config import settings

logger = structlog.get_logger()


class MetaService:
    """Meta Ads operations for brain API."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_meta_client(self, tenant_id: str) -> MetaAdsClient:
        """Get authenticated Meta Ads client from DB integration record."""
        from app.models.v2.integration_meta import IntegrationMeta
        result = await self.db.execute(
            select(IntegrationMeta).where(IntegrationMeta.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            raise ValueError("No Meta Ads integration found for this tenant")
        return MetaAdsClient(
            ad_account_id=integration.ad_account_id,
            access_token_encrypted=integration.access_token_encrypted,
        )

    # ── Account ────────────────────────────────────────────────

    async def get_account_info(self, tenant_id: str) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_account_info()

    # ── Campaigns ──────────────────────────────────────────────

    async def get_campaigns(self, tenant_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_campaigns(status_filter)

    async def get_campaign_insights(
        self, tenant_id: str, campaign_id: str,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_campaign_insights(campaign_id, date_from, date_to)

    async def get_all_performance(
        self, tenant_id: str,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_all_campaign_performance(date_from, date_to)

    async def create_campaign(
        self, tenant_id: str, name: str,
        objective: str = "OUTCOME_LEADS", daily_budget: int = 2000,
        status: str = "PAUSED",
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.create_campaign(name, objective, daily_budget, status)

    async def update_campaign_status(self, tenant_id: str, campaign_id: str, status: str) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.update_campaign_status(campaign_id, status)

    async def update_campaign_budget(self, tenant_id: str, campaign_id: str, daily_budget: int) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.update_campaign_budget(campaign_id, daily_budget)

    # ── Ad Sets ────────────────────────────────────────────────

    async def get_adsets(self, tenant_id: str, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_adsets(campaign_id)

    async def get_adset_insights(
        self, tenant_id: str, adset_id: str,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_adset_insights(adset_id, date_from, date_to)

    async def create_adset(
        self, tenant_id: str, campaign_id: str, name: str,
        daily_budget: int = 2000, optimization_goal: str = "LEAD_GENERATION",
        targeting: Optional[Dict] = None, status: str = "PAUSED",
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.create_adset(
            campaign_id, name, daily_budget, optimization_goal,
            targeting=targeting, status=status,
        )

    # ── Ads & Creatives ────────────────────────────────────────

    async def get_ads(self, tenant_id: str, adset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_ads(adset_id)

    async def get_ad_insights(
        self, tenant_id: str, ad_id: str,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_ad_insights(ad_id, date_from, date_to)

    async def create_ad_creative(
        self, tenant_id: str, name: str, page_id: str, message: str,
        link: Optional[str] = None, image_url: Optional[str] = None,
        call_to_action_type: str = "LEARN_MORE",
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.create_ad_creative(
            name, page_id, message, link, image_url, call_to_action_type,
        )

    async def create_ad(
        self, tenant_id: str, adset_id: str, name: str,
        creative_id: str, status: str = "PAUSED",
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.create_ad(adset_id, name, creative_id, status)

    async def ai_create_ad_creative(
        self, tenant_id: str, page_id: str,
        business_name: str, business_type: str, topic: str,
        link: Optional[str] = None, cta_type: str = "LEARN_MORE",
        include_image: bool = True,
    ) -> Dict[str, Any]:
        """Use AI to generate ad copy + image, then create creative."""
        import anthropic
        claude = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""Write Facebook/Instagram ad copy for this business.

Business: {business_name} ({business_type})
Topic/Offer: {topic}

Rules:
- Primary text: 1-2 sentences, compelling hook + value prop (under 125 chars ideal)
- Keep it conversational and scroll-stopping
- Include a clear benefit for the customer
- Do not use hashtags
- Return ONLY the ad text, nothing else

Ad copy:"""

        response = claude.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        ad_text = response.content[0].text.strip()

        # Generate image if requested
        image_url = None
        image_result = None
        if include_image:
            img_client = ImageGeneratorClient()
            if img_client.is_configured:
                image_result = await img_client.generate_ad_image(
                    service=topic,
                    business_name=business_name,
                    business_type=business_type,
                    engine="dalle",
                    style="photorealistic",
                    size="1080x1080",
                )
                if image_result.get("success"):
                    image_url = image_result.get("image_url")

        # Create the creative
        client = await self._get_meta_client(tenant_id)
        creative_name = f"AI - {topic[:40]}"
        result = await client.create_ad_creative(
            name=creative_name, page_id=page_id, message=ad_text,
            link=link, image_url=image_url, call_to_action_type=cta_type,
        )
        result["ai_generated_text"] = ad_text
        if image_result:
            result["image"] = image_result
        return result

    # ── Audiences ──────────────────────────────────────────────

    async def get_audiences(self, tenant_id: str) -> List[Dict[str, Any]]:
        client = await self._get_meta_client(tenant_id)
        return await client.get_custom_audiences()

    # ── Full Context / Audit ───────────────────────────────────

    async def build_full_context(
        self, tenant_id: str,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._get_meta_client(tenant_id)
        return await client.build_full_context(date_from, date_to)

    async def ai_audit(self, tenant_id: str) -> Dict[str, Any]:
        """Run full account audit with Claude analysis."""
        import anthropic
        context = await self.build_full_context(tenant_id)

        claude = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = f"""Analyze this Meta Ads account data and provide an audit.

Account Data:
{context}

Provide:
1. Account health score (1-10)
2. Top 3 issues found
3. Top 3 opportunities
4. Budget efficiency rating
5. Specific recommendations with expected impact

Be specific with numbers. Reference actual campaign names and metrics."""

        response = claude.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        return {
            "audit": response.content[0].text.strip(),
            "context_summary": context.get("heuristics", {}),
        }

    # ── Health ─────────────────────────────────────────────────

    async def health_check(self, tenant_id: str) -> Dict[str, Any]:
        try:
            client = await self._get_meta_client(tenant_id)
            info = await client.get_account_info()
            return {
                "status": "healthy",
                "account": info.get("name", "Unknown"),
                "account_id": info.get("account_id"),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}
