import uuid
from datetime import date, datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, BigInteger, Integer, Date, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SearchTermPerformance(Base):
    __tablename__ = "search_term_performance"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ad_group_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    keyword_id: Mapped[str] = mapped_column(String(30), nullable=True)
    keyword_text: Mapped[str] = mapped_column(String(500), nullable=True)
    search_term: Mapped[str] = mapped_column(String(500), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_value: Mapped[float] = mapped_column(Float, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    average_cpc_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
