"""
Revenue Attribution Service — IntelliDrive attribution chain:
Keyword -> Click -> Call/Lead -> Job -> Invoice -> Revenue

Connects Google Ads spend to actual business revenue for true ROAS
calculation, replacing Google's estimated conversion-value ROAS with
real invoice data from the business CRM/invoicing system.
"""
import uuid
import structlog
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    and_,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.performance_daily import PerformanceDaily

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# SQLAlchemy Model
# ---------------------------------------------------------------------------

class RevenueAttribution(Base):
    __tablename__ = "revenue_attributions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Google Ads linkage
    campaign_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    ad_group_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    keyword_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    keyword_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    click_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Google gclid

    # Conversion event
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # call, form_submit, booking, walk_in
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Lead details
    caller_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    lead_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lead_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Job / invoice linkage
    job_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    job_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    invoice_amount_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    revenue_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ad cost attribution
    cost_micros: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RevenueAttributionService:
    """Links Google Ads spend to actual business revenue for true ROAS."""

    def __init__(self, db: AsyncSession, tenant_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # Record a new conversion event
    # ------------------------------------------------------------------
    async def record_conversion_event(
        self,
        event_type: str,
        source_data: Dict[str, Any],
    ) -> RevenueAttribution:
        """
        Record a conversion event (call, form_submit, booking, walk_in).

        ``source_data`` may include: caller_phone, lead_name, lead_email,
        click_id, campaign_id, keyword_text, and any other lead fields.
        """
        try:
            record = RevenueAttribution(
                tenant_id=self.tenant_id,
                event_type=event_type,
                event_timestamp=source_data.get(
                    "event_timestamp", datetime.now(timezone.utc)
                ),
                caller_phone=source_data.get("caller_phone"),
                lead_name=source_data.get("lead_name"),
                lead_email=source_data.get("lead_email"),
                click_id=source_data.get("click_id"),
                campaign_id=source_data.get("campaign_id"),
                ad_group_id=source_data.get("ad_group_id"),
                keyword_text=source_data.get("keyword_text"),
                keyword_id=source_data.get("keyword_id"),
                notes=source_data.get("notes"),
            )
            self.db.add(record)
            await self.db.flush()
            logger.info(
                "revenue_attribution.event_recorded",
                tenant_id=self.tenant_id,
                event_type=event_type,
                attribution_id=record.id,
            )
            return record
        except Exception:
            logger.exception(
                "revenue_attribution.record_event_failed",
                tenant_id=self.tenant_id,
                event_type=event_type,
            )
            raise

    # ------------------------------------------------------------------
    # Link conversion to its Google Ads source
    # ------------------------------------------------------------------
    async def link_to_campaign(
        self,
        conversion_id: str,
        campaign_id: str,
        keyword_text: Optional[str] = None,
        click_id: Optional[str] = None,
    ) -> Optional[RevenueAttribution]:
        """Attach Google Ads campaign/keyword/click data to a conversion."""
        try:
            record = await self.db.get(RevenueAttribution, conversion_id)
            if not record or record.tenant_id != self.tenant_id:
                logger.warning(
                    "revenue_attribution.link_not_found",
                    conversion_id=conversion_id,
                    tenant_id=self.tenant_id,
                )
                return None

            record.campaign_id = campaign_id
            if keyword_text is not None:
                record.keyword_text = keyword_text
            if click_id is not None:
                record.click_id = click_id
            record.updated_at = datetime.now(timezone.utc)

            await self.db.flush()
            logger.info(
                "revenue_attribution.linked_to_campaign",
                attribution_id=conversion_id,
                campaign_id=campaign_id,
            )
            return record
        except Exception:
            logger.exception(
                "revenue_attribution.link_failed",
                conversion_id=conversion_id,
            )
            raise

    # ------------------------------------------------------------------
    # Attach actual invoice revenue to a conversion
    # ------------------------------------------------------------------
    async def record_job_revenue(
        self,
        conversion_id: str,
        job_id: str,
        invoice_amount: int,
        invoice_date: date,
    ) -> Optional[RevenueAttribution]:
        """
        Link actual revenue to a conversion.

        ``invoice_amount`` is in cents (e.g. 15000 = $150.00).
        """
        try:
            record = await self.db.get(RevenueAttribution, conversion_id)
            if not record or record.tenant_id != self.tenant_id:
                logger.warning(
                    "revenue_attribution.job_revenue_not_found",
                    conversion_id=conversion_id,
                )
                return None

            record.job_id = job_id
            record.invoice_amount_cents = invoice_amount
            record.invoice_date = invoice_date
            record.revenue_confirmed = True
            record.updated_at = datetime.now(timezone.utc)

            await self.db.flush()
            logger.info(
                "revenue_attribution.job_revenue_recorded",
                attribution_id=conversion_id,
                job_id=job_id,
                invoice_amount_cents=invoice_amount,
            )
            return record
        except Exception:
            logger.exception(
                "revenue_attribution.job_revenue_failed",
                conversion_id=conversion_id,
            )
            raise

    # ------------------------------------------------------------------
    # True ROAS for a campaign
    # ------------------------------------------------------------------
    async def get_true_roas(
        self,
        campaign_id: str,
        date_range_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Calculate real ROAS from confirmed invoices vs actual ad spend.

        Returns dict with total_revenue_cents, total_spend_micros,
        true_roas, and google_roas (estimated from conv_value).
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=date_range_days)

            # Sum confirmed invoice revenue from attributions
            rev_q = (
                select(
                    func.coalesce(func.sum(RevenueAttribution.invoice_amount_cents), 0).label(
                        "total_revenue_cents"
                    ),
                    func.count(RevenueAttribution.id).label("job_count"),
                )
                .where(
                    and_(
                        RevenueAttribution.tenant_id == self.tenant_id,
                        RevenueAttribution.campaign_id == campaign_id,
                        RevenueAttribution.revenue_confirmed.is_(True),
                        RevenueAttribution.event_timestamp >= cutoff,
                    )
                )
            )
            rev_result = await self.db.execute(rev_q)
            rev_row = rev_result.one()
            total_revenue_cents: int = rev_row.total_revenue_cents
            job_count: int = rev_row.job_count

            # Sum ad spend from performance_daily for the same campaign
            spend_q = (
                select(
                    func.coalesce(func.sum(PerformanceDaily.cost_micros), 0).label(
                        "total_spend_micros"
                    ),
                    func.coalesce(func.sum(PerformanceDaily.conv_value), 0.0).label(
                        "google_conv_value"
                    ),
                )
                .where(
                    and_(
                        PerformanceDaily.tenant_id == self.tenant_id,
                        PerformanceDaily.entity_type == "campaign",
                        PerformanceDaily.entity_id == campaign_id,
                        PerformanceDaily.date >= cutoff.date(),
                    )
                )
            )
            spend_result = await self.db.execute(spend_q)
            spend_row = spend_result.one()
            total_spend_micros: int = spend_row.total_spend_micros
            google_conv_value: float = spend_row.google_conv_value

            # Calculate true ROAS: revenue_dollars / spend_dollars
            spend_dollars = total_spend_micros / 1_000_000 if total_spend_micros else 0
            revenue_dollars = total_revenue_cents / 100 if total_revenue_cents else 0

            true_roas = (revenue_dollars / spend_dollars) if spend_dollars > 0 else 0.0
            google_roas = (google_conv_value / spend_dollars) if spend_dollars > 0 else 0.0

            return {
                "campaign_id": campaign_id,
                "date_range_days": date_range_days,
                "total_revenue_cents": total_revenue_cents,
                "total_revenue_dollars": revenue_dollars,
                "total_spend_micros": total_spend_micros,
                "total_spend_dollars": spend_dollars,
                "job_count": job_count,
                "true_roas": round(true_roas, 2),
                "google_roas": round(google_roas, 2),
            }
        except Exception:
            logger.exception(
                "revenue_attribution.get_true_roas_failed",
                campaign_id=campaign_id,
            )
            raise

    # ------------------------------------------------------------------
    # Keywords that generated actual revenue
    # ------------------------------------------------------------------
    async def get_keyword_revenue(
        self,
        campaign_id: str,
    ) -> List[Dict[str, Any]]:
        """Which keywords for a campaign generated confirmed revenue."""
        try:
            q = (
                select(
                    RevenueAttribution.keyword_text,
                    func.count(RevenueAttribution.id).label("jobs"),
                    func.coalesce(func.sum(RevenueAttribution.invoice_amount_cents), 0).label(
                        "total_revenue_cents"
                    ),
                )
                .where(
                    and_(
                        RevenueAttribution.tenant_id == self.tenant_id,
                        RevenueAttribution.campaign_id == campaign_id,
                        RevenueAttribution.revenue_confirmed.is_(True),
                        RevenueAttribution.keyword_text.isnot(None),
                    )
                )
                .group_by(RevenueAttribution.keyword_text)
                .order_by(func.sum(RevenueAttribution.invoice_amount_cents).desc())
            )
            result = await self.db.execute(q)
            rows = result.all()
            return [
                {
                    "keyword_text": row.keyword_text,
                    "jobs": row.jobs,
                    "total_revenue_cents": row.total_revenue_cents,
                    "total_revenue_dollars": row.total_revenue_cents / 100,
                }
                for row in rows
            ]
        except Exception:
            logger.exception(
                "revenue_attribution.get_keyword_revenue_failed",
                campaign_id=campaign_id,
            )
            raise

    # ------------------------------------------------------------------
    # Full attribution report across all campaigns
    # ------------------------------------------------------------------
    async def get_attribution_report(
        self,
        tenant_id: str,
        date_range_days: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Full report per campaign: spend, clicks, calls, jobs, revenue, true ROAS.

        Uses the provided ``tenant_id`` (allows cross-tenant admin queries).
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=date_range_days)

            # Attribution aggregates per campaign
            attr_q = (
                select(
                    RevenueAttribution.campaign_id,
                    func.count(RevenueAttribution.id).label("total_conversions"),
                    func.count(
                        func.nullif(RevenueAttribution.revenue_confirmed, False)
                    ).label("confirmed_jobs"),
                    func.coalesce(
                        func.sum(
                            func.case(
                                (RevenueAttribution.revenue_confirmed.is_(True),
                                 RevenueAttribution.invoice_amount_cents),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("total_revenue_cents"),
                )
                .where(
                    and_(
                        RevenueAttribution.tenant_id == tenant_id,
                        RevenueAttribution.campaign_id.isnot(None),
                        RevenueAttribution.event_timestamp >= cutoff,
                    )
                )
                .group_by(RevenueAttribution.campaign_id)
            )
            attr_result = await self.db.execute(attr_q)
            attr_rows = {row.campaign_id: row for row in attr_result.all()}

            # Spend aggregates per campaign from performance_daily
            spend_q = (
                select(
                    PerformanceDaily.entity_id.label("campaign_id"),
                    func.coalesce(func.sum(PerformanceDaily.cost_micros), 0).label(
                        "total_spend_micros"
                    ),
                    func.coalesce(func.sum(PerformanceDaily.clicks), 0).label(
                        "total_clicks"
                    ),
                    func.coalesce(func.sum(PerformanceDaily.conversions), 0.0).label(
                        "google_conversions"
                    ),
                    func.coalesce(func.sum(PerformanceDaily.conv_value), 0.0).label(
                        "google_conv_value"
                    ),
                )
                .where(
                    and_(
                        PerformanceDaily.tenant_id == tenant_id,
                        PerformanceDaily.entity_type == "campaign",
                        PerformanceDaily.date >= cutoff.date(),
                    )
                )
                .group_by(PerformanceDaily.entity_id)
            )
            spend_result = await self.db.execute(spend_q)
            spend_rows = {row.campaign_id: row for row in spend_result.all()}

            # Merge
            all_campaign_ids = set(attr_rows.keys()) | set(spend_rows.keys())
            report: List[Dict[str, Any]] = []

            for cid in sorted(all_campaign_ids):
                attr = attr_rows.get(cid)
                spend = spend_rows.get(cid)

                spend_micros = spend.total_spend_micros if spend else 0
                spend_dollars = spend_micros / 1_000_000
                revenue_cents = attr.total_revenue_cents if attr else 0
                revenue_dollars = revenue_cents / 100

                true_roas = (revenue_dollars / spend_dollars) if spend_dollars > 0 else 0.0

                report.append(
                    {
                        "campaign_id": cid,
                        "total_spend_micros": spend_micros,
                        "total_spend_dollars": spend_dollars,
                        "total_clicks": spend.total_clicks if spend else 0,
                        "google_conversions": spend.google_conversions if spend else 0.0,
                        "google_conv_value": spend.google_conv_value if spend else 0.0,
                        "total_conversions": attr.total_conversions if attr else 0,
                        "confirmed_jobs": attr.confirmed_jobs if attr else 0,
                        "total_revenue_cents": revenue_cents,
                        "total_revenue_dollars": revenue_dollars,
                        "true_roas": round(true_roas, 2),
                    }
                )

            return report
        except Exception:
            logger.exception(
                "revenue_attribution.get_attribution_report_failed",
                tenant_id=tenant_id,
            )
            raise

    # ------------------------------------------------------------------
    # Top revenue keywords across all campaigns
    # ------------------------------------------------------------------
    async def get_top_revenue_keywords(
        self,
        tenant_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Keywords ranked by actual confirmed revenue across all campaigns."""
        try:
            q = (
                select(
                    RevenueAttribution.keyword_text,
                    RevenueAttribution.campaign_id,
                    func.count(RevenueAttribution.id).label("jobs"),
                    func.coalesce(func.sum(RevenueAttribution.invoice_amount_cents), 0).label(
                        "total_revenue_cents"
                    ),
                    func.avg(RevenueAttribution.invoice_amount_cents).label(
                        "avg_revenue_cents"
                    ),
                )
                .where(
                    and_(
                        RevenueAttribution.tenant_id == tenant_id,
                        RevenueAttribution.revenue_confirmed.is_(True),
                        RevenueAttribution.keyword_text.isnot(None),
                    )
                )
                .group_by(
                    RevenueAttribution.keyword_text,
                    RevenueAttribution.campaign_id,
                )
                .order_by(func.sum(RevenueAttribution.invoice_amount_cents).desc())
                .limit(limit)
            )
            result = await self.db.execute(q)
            rows = result.all()
            return [
                {
                    "keyword_text": row.keyword_text,
                    "campaign_id": row.campaign_id,
                    "jobs": row.jobs,
                    "total_revenue_cents": row.total_revenue_cents,
                    "total_revenue_dollars": row.total_revenue_cents / 100,
                    "avg_revenue_cents": int(row.avg_revenue_cents) if row.avg_revenue_cents else 0,
                    "avg_revenue_dollars": round(row.avg_revenue_cents / 100, 2)
                    if row.avg_revenue_cents
                    else 0,
                }
                for row in rows
            ]
        except Exception:
            logger.exception(
                "revenue_attribution.get_top_keywords_failed",
                tenant_id=tenant_id,
            )
            raise
