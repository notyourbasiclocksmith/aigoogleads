import uuid
from datetime import date, datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Date, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AuctionInsight(Base):
    __tablename__ = "auction_insights"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    competitor_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    impression_share: Mapped[float] = mapped_column(Float, default=0.0)
    overlap_rate: Mapped[float] = mapped_column(Float, default=0.0)
    outranking_share: Mapped[float] = mapped_column(Float, default=0.0)
    top_of_page_rate: Mapped[float] = mapped_column(Float, default=0.0)
    abs_top_rate: Mapped[float] = mapped_column(Float, default=0.0)
    position_above_rate: Mapped[float] = mapped_column(Float, default=0.0)
