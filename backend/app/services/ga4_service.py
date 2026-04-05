"""
GA4 (Google Analytics 4) Service — fetches analytics data via GA4 Data API.

Provides: sessions, users, pageviews, conversions, traffic sources, landing pages,
device breakdown, geographic data, and real-time active users.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_token
from app.models.v2.integration_ga4 import IntegrationGA4

logger = structlog.get_logger()


class GA4Service:
    """Fetches data from GA4 Data API for a tenant's connected property."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_ga4_client(self, tenant_id: str):
        """Get authenticated GA4 Data API client."""
        result = await self.db.execute(
            select(IntegrationGA4).where(IntegrationGA4.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            raise ValueError("No GA4 property connected")
        if not integration.refresh_token_encrypted:
            raise ValueError("GA4 refresh token not configured")

        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2.credentials import Credentials

        refresh_token = decrypt_token(integration.refresh_token_encrypted)
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=settings.GA4_CLIENT_ID,
            client_secret=settings.GA4_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
        )
        client = BetaAnalyticsDataClient(credentials=creds)
        return client, integration.property_id

    def _run_report(self, client, property_id: str, dimensions: list, metrics: list,
                    date_from: str = "30daysAgo", date_to: str = "today",
                    limit: int = 100, order_by: Optional[str] = None):
        """Execute a GA4 runReport call and return parsed rows."""
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric, OrderBy,
        )
        dim_objs = [Dimension(name=d) for d in dimensions]
        met_objs = [Metric(name=m) for m in metrics]
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=dim_objs,
            metrics=met_objs,
            date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
            limit=limit,
        )
        if order_by:
            request.order_bys = [OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_by), desc=True)]
        response = client.run_report(request)
        rows = []
        for row in response.rows:
            entry = {}
            for i, dim in enumerate(dimensions):
                entry[dim] = row.dimension_values[i].value
            for i, met in enumerate(metrics):
                val = row.metric_values[i].value
                entry[met] = float(val) if "." in val else int(val)
            rows.append(entry)
        return rows

    # ── Public Methods ──────────────────────────────────────────

    async def get_status(self, tenant_id: str) -> Dict[str, Any]:
        """Check GA4 connection status."""
        result = await self.db.execute(
            select(IntegrationGA4).where(IntegrationGA4.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            return {"connected": False}
        return {
            "connected": True,
            "property_id": integration.property_id,
            "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
        }

    async def get_overview(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """High-level GA4 metrics: sessions, users, pageviews, bounce rate, avg session duration."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Metric,
        )
        request = RunReportRequest(
            property=f"properties/{prop_id}",
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="newUsers"),
                Metric(name="screenPageViews"),
                Metric(name="bounceRate"),
                Metric(name="averageSessionDuration"),
                Metric(name="conversions"),
                Metric(name="engagedSessions"),
            ],
            date_ranges=[DateRange(start_date=date_from, end_date=date_to)],
        )
        response = client.run_report(request)
        metrics = {}
        metric_names = ["sessions", "totalUsers", "newUsers", "screenPageViews",
                       "bounceRate", "averageSessionDuration", "conversions", "engagedSessions"]
        for row in response.rows:
            for i, name in enumerate(metric_names):
                val = row.metric_values[i].value
                metrics[name] = float(val) if "." in val else int(val)
        return {"property_id": prop_id, "date_range": {"from": date_from, "to": date_to}, "metrics": metrics}

    async def get_traffic_sources(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Traffic by source/medium."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["sessionSource", "sessionMedium"],
            metrics=["sessions", "totalUsers", "conversions", "bounceRate"],
            date_from=date_from, date_to=date_to, limit=50,
            order_by="sessions",
        )
        return {"sources": rows, "count": len(rows)}

    async def get_landing_pages(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Top landing pages by sessions."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["landingPage"],
            metrics=["sessions", "totalUsers", "conversions", "bounceRate", "averageSessionDuration"],
            date_from=date_from, date_to=date_to, limit=50,
            order_by="sessions",
        )
        return {"landing_pages": rows, "count": len(rows)}

    async def get_device_breakdown(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Sessions by device category."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["deviceCategory"],
            metrics=["sessions", "totalUsers", "conversions", "bounceRate"],
            date_from=date_from, date_to=date_to,
        )
        return {"devices": rows}

    async def get_geo_performance(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Sessions by city."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["city", "region"],
            metrics=["sessions", "totalUsers", "conversions"],
            date_from=date_from, date_to=date_to, limit=50,
            order_by="sessions",
        )
        return {"geo": rows, "count": len(rows)}

    async def get_daily_trend(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Daily trend data."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["date"],
            metrics=["sessions", "totalUsers", "conversions", "screenPageViews"],
            date_from=date_from, date_to=date_to, limit=90,
        )
        rows.sort(key=lambda r: r.get("date", ""))
        return {"daily": rows, "count": len(rows)}

    async def get_conversion_events(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Conversion events breakdown."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["eventName"],
            metrics=["conversions", "totalUsers"],
            date_from=date_from, date_to=date_to, limit=30,
            order_by="conversions",
        )
        return {"events": rows, "count": len(rows)}

    async def get_page_performance(
        self, tenant_id: str, date_from: str = "30daysAgo", date_to: str = "today",
    ) -> Dict[str, Any]:
        """Top pages by pageviews."""
        client, prop_id = await self._get_ga4_client(tenant_id)
        rows = self._run_report(
            client, prop_id,
            dimensions=["pagePath", "pageTitle"],
            metrics=["screenPageViews", "totalUsers", "averageSessionDuration", "bounceRate"],
            date_from=date_from, date_to=date_to, limit=50,
            order_by="screenPageViews",
        )
        return {"pages": rows, "count": len(rows)}
