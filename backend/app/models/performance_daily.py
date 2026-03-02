import uuid
from datetime import date, datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, BigInteger, Integer, Date, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PerformanceDaily(Base):
    __tablename__ = "performance_daily"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # campaign, ad_group, ad, keyword
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    conversions: Mapped[float] = mapped_column(Float, default=0.0)
    conv_value: Mapped[float] = mapped_column(Float, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    cpc_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    cpa_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict)
