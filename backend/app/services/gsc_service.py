"""
Google Search Console Service — fetches organic search data via GSC API.

Provides: queries, pages, countries, devices, impressions, clicks, CTR, position.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_token

logger = structlog.get_logger()


class GSCService:
    """Fetches data from Google Search Console API."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_gsc_client(self, tenant_id: str):
        """Get authenticated GSC client + site URL."""
        # GSC shares OAuth with GA4 or Google Ads. Check for a GSC-specific
        # config first, then fall back to GA4 integration credentials.
        from app.models.v2.integration_ga4 import IntegrationGA4

        result = await self.db.execute(
            select(IntegrationGA4).where(IntegrationGA4.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration or not integration.refresh_token_encrypted:
            raise ValueError("No Google integration with Search Console access")

        refresh_token = decrypt_token(integration.refresh_token_encrypted)
        site_url = integration.config_json.get("gsc_site_url") if integration.config_json else None
        if not site_url:
            raise ValueError("GSC site URL not configured — set gsc_site_url in GA4 config_json")

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=settings.GA4_CLIENT_ID,
            client_secret=settings.GA4_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
        )
        service = build("searchconsole", "v1", credentials=creds)
        return service, site_url

    def _default_dates(self, date_from: Optional[str], date_to: Optional[str]):
        today = datetime.now(timezone.utc).date()
        if not date_to:
            date_to = (today - timedelta(days=3)).isoformat()  # GSC data lags ~3 days
        if not date_from:
            date_from = (today - timedelta(days=30)).isoformat()
        return date_from, date_to

    def _query_gsc(self, service, site_url: str, dimensions: list,
                   date_from: str, date_to: str, row_limit: int = 100,
                   dimension_filters: Optional[list] = None) -> List[Dict[str, Any]]:
        """Execute a GSC searchAnalytics.query call."""
        body = {
            "startDate": date_from,
            "endDate": date_to,
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        if dimension_filters:
            body["dimensionFilterGroups"] = [{"filters": dimension_filters}]
        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        rows = []
        for row in response.get("rows", []):
            entry = {}
            for i, dim in enumerate(dimensions):
                entry[dim] = row["keys"][i]
            entry["clicks"] = row.get("clicks", 0)
            entry["impressions"] = row.get("impressions", 0)
            entry["ctr"] = round(row.get("ctr", 0) * 100, 2)
            entry["position"] = round(row.get("position", 0), 1)
            rows.append(entry)
        return rows

    # ── Public Methods ──────────────────────────────────────────

    async def get_status(self, tenant_id: str) -> Dict[str, Any]:
        """Check GSC connection status."""
        try:
            service, site_url = await self._get_gsc_client(tenant_id)
            return {"connected": True, "site_url": site_url}
        except ValueError as e:
            return {"connected": False, "error": str(e)}

    async def get_top_queries(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None, limit: int = 100,
    ) -> Dict[str, Any]:
        """Top search queries by clicks."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["query"], date_from, date_to, limit)
        rows.sort(key=lambda r: r.get("clicks", 0), reverse=True)
        total_clicks = sum(r["clicks"] for r in rows)
        total_impressions = sum(r["impressions"] for r in rows)
        return {
            "queries": rows, "count": len(rows),
            "totals": {"clicks": total_clicks, "impressions": total_impressions},
        }

    async def get_top_pages(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None, limit: int = 100,
    ) -> Dict[str, Any]:
        """Top pages by clicks."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["page"], date_from, date_to, limit)
        rows.sort(key=lambda r: r.get("clicks", 0), reverse=True)
        return {"pages": rows, "count": len(rows)}

    async def get_query_page_matrix(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None, limit: int = 200,
    ) -> Dict[str, Any]:
        """Query + page combinations — shows which page ranks for which query."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["query", "page"], date_from, date_to, limit)
        return {"query_pages": rows, "count": len(rows)}

    async def get_country_performance(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Performance by country."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["country"], date_from, date_to, 50)
        return {"countries": rows, "count": len(rows)}

    async def get_device_performance(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Performance by device type."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["device"], date_from, date_to)
        return {"devices": rows}

    async def get_daily_trend(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Daily organic search trend."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["date"], date_from, date_to, 90)
        rows.sort(key=lambda r: r.get("date", ""))
        return {"daily": rows, "count": len(rows)}

    async def get_search_appearance(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Performance by search appearance (rich results, AMP, etc.)."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)
        rows = self._query_gsc(service, site_url, ["searchAppearance"], date_from, date_to)
        return {"appearances": rows}

    async def get_overview(
        self, tenant_id: str, date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Overview: aggregate metrics + top 10 queries + top 10 pages."""
        service, site_url = await self._get_gsc_client(tenant_id)
        date_from, date_to = self._default_dates(date_from, date_to)

        # Aggregate totals (no dimensions)
        body = {"startDate": date_from, "endDate": date_to}
        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        totals = {}
        for row in response.get("rows", []):
            totals = {
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": round(row.get("ctr", 0) * 100, 2),
                "position": round(row.get("position", 0), 1),
            }

        # Top queries
        top_queries = self._query_gsc(service, site_url, ["query"], date_from, date_to, 10)
        # Top pages
        top_pages = self._query_gsc(service, site_url, ["page"], date_from, date_to, 10)

        return {
            "site_url": site_url,
            "date_range": {"from": date_from, "to": date_to},
            "totals": totals,
            "top_queries": top_queries,
            "top_pages": top_pages,
        }
