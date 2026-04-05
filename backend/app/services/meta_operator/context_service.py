"""
Meta Ads Context Service — builds full account context for Claude analysis.
"""
from typing import Dict, Any
import structlog

from app.integrations.meta_ads.client import MetaAdsClient

logger = structlog.get_logger()


class MetaAdsContextService:
    """Fetches and normalizes Meta Ads data for Claude consumption."""

    def __init__(self, client: MetaAdsClient):
        self.client = client

    async def build_full_context(
        self, date_from: str = None, date_to: str = None,
    ) -> Dict[str, Any]:
        """Build complete account context for Claude."""
        return await self.client.build_full_context(date_from, date_to)
