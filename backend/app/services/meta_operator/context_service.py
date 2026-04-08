"""
Meta Ads Context Service — builds full account context for Claude analysis.
"""
from typing import Dict, Any, Optional
import structlog

from app.integrations.meta_ads.client import MetaAdsClient

logger = structlog.get_logger()


class MetaAdsContextService:
    """Fetches and normalizes Meta Ads data for Claude consumption."""

    def __init__(
        self,
        client: MetaAdsClient,
        pixel_id: Optional[str] = None,
        page_id: Optional[str] = None,
        page_name: Optional[str] = None,
    ):
        self.client = client
        self.pixel_id = pixel_id
        self.page_id = page_id
        self.page_name = page_name

    async def build_full_context(
        self, date_from: str = None, date_to: str = None,
    ) -> Dict[str, Any]:
        """Build complete account context for Claude."""
        context = await self.client.build_full_context(date_from, date_to)
        if self.pixel_id:
            context["pixel_id"] = self.pixel_id
        if self.page_id:
            context["page_id"] = self.page_id
            context["page_name"] = self.page_name or "Unknown Page"
        return context
