import uuid
from datetime import date, datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, BigInteger, Integer, Date, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class KeywordPerformanceDaily(Base):
    __tablename__ = "keyword_performance_daily"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ad_group_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    keyword_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    keyword_text: Mapped[str] = mapped_column(String(500), nullable=True)
    match_type: Mapped[str] = mapped_column(String(20), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0.0)
    conversion_value: Mapped[float] = mapped_column(Float, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    average_cpc_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    quality_score: Mapped[int] = mapped_column(Integer, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
