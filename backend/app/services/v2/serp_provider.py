"""
Module 8 — SERP Provider Abstraction
Pluggable SERP search interface with caching and rate limiting.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import json
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.models.serp_scan import SerpScan

logger = structlog.get_logger()


class SerpResult:
    def __init__(self, keyword: str, geo: str, device: str, organic: list, ads: list, raw: dict):
        self.keyword = keyword
        self.geo = geo
        self.device = device
        self.organic = organic
        self.ads = ads
        self.raw = raw


class BaseSerpProvider(ABC):
    """Abstract SERP provider interface."""

    provider_name: str = "base"

    @abstractmethod
    async def search(self, keyword: str, geo: str = "US", device: str = "desktop") -> SerpResult:
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        ...


class MockSerpProvider(BaseSerpProvider):
    """Local development mock provider."""
    provider_name = "mock"

    async def search(self, keyword: str, geo: str = "US", device: str = "desktop") -> SerpResult:
        return SerpResult(
            keyword=keyword,
            geo=geo,
            device=device,
            organic=[
                {"position": 1, "title": f"Best {keyword} Services", "domain": "example.com", "url": "https://example.com"},
                {"position": 2, "title": f"Top {keyword} Near You", "domain": "competitor1.com", "url": "https://competitor1.com"},
                {"position": 3, "title": f"{keyword} - Professional Service", "domain": "competitor2.com", "url": "https://competitor2.com"},
            ],
            ads=[
                {"position": 1, "title": f"#{keyword} Experts | Call Now", "domain": "advertiser1.com", "description": "Professional service, licensed & insured."},
                {"position": 2, "title": f"Affordable {keyword}", "domain": "advertiser2.com", "description": "Get a free quote today."},
            ],
            raw={"mock": True, "keyword": keyword, "geo": geo, "device": device},
        )

    async def health_check(self) -> Dict[str, Any]:
        return {"healthy": True, "provider": "mock"}


class SerpApiProvider(BaseSerpProvider):
    """Stub for a real SERP API provider (e.g., SerpAPI, ValueSERP, DataForSEO)."""
    provider_name = "serp_api"

    def __init__(self):
        self.api_key = settings.SERP_PROVIDER_KEY if hasattr(settings, "SERP_PROVIDER_KEY") else ""

    async def search(self, keyword: str, geo: str = "US", device: str = "desktop") -> SerpResult:
        if not self.api_key:
            logger.warning("SERP provider API key not configured, falling back to mock")
            return await MockSerpProvider().search(keyword, geo, device)

        # Stub: would call external SERP API
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://serpapi.example.com/search",
                    params={"q": keyword, "gl": geo, "device": device, "api_key": self.api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                return SerpResult(
                    keyword=keyword, geo=geo, device=device,
                    organic=data.get("organic_results", []),
                    ads=data.get("ads", []),
                    raw=data,
                )
        except Exception as e:
            logger.error("SERP API request failed", error=str(e))
            return await MockSerpProvider().search(keyword, geo, device)

    async def health_check(self) -> Dict[str, Any]:
        return {"healthy": bool(self.api_key), "provider": "serp_api", "configured": bool(self.api_key)}


# ── Provider Registry ──
PROVIDER_REGISTRY: Dict[str, type] = {
    "mock": MockSerpProvider,
    "serp_api": SerpApiProvider,
}


def get_serp_provider(provider_name: Optional[str] = None) -> BaseSerpProvider:
    name = provider_name or ("serp_api" if getattr(settings, "SERP_PROVIDER_KEY", "") else "mock")
    cls = PROVIDER_REGISTRY.get(name, MockSerpProvider)
    return cls()


# ── Cached SERP search with rate control ──
async def cached_serp_search(
    db: AsyncSession,
    tenant_id: str,
    keyword: str,
    geo: str = "US",
    device: str = "desktop",
    cache_hours: int = 24,
    provider_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Search SERP with caching to control frequency and cost."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cache_hours)
    stmt = select(SerpScan).where(
        and_(
            SerpScan.tenant_id == tenant_id,
            SerpScan.keyword == keyword,
            SerpScan.created_at >= cutoff,
        )
    ).order_by(SerpScan.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    cached = result.scalars().first()

    if cached and cached.results_json:
        return {"cached": True, "data": cached.results_json, "scanned_at": cached.created_at.isoformat()}

    provider = get_serp_provider(provider_name)
    serp_result = await provider.search(keyword, geo, device)

    scan = SerpScan(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        keyword=keyword,
        geo=geo,
        device=device,
        results_json={
            "organic": serp_result.organic,
            "ads": serp_result.ads,
            "provider": provider.provider_name,
        },
    )
    db.add(scan)

    return {"cached": False, "data": scan.results_json, "scanned_at": datetime.now(timezone.utc).isoformat()}
