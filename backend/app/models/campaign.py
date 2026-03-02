import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # SEARCH, PERFORMANCE_MAX, CALL, DISPLAY, REMARKETING
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")  # DRAFT, ENABLED, PAUSED, REMOVED
    objective: Mapped[str] = mapped_column(String(50), nullable=True)
    budget_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    bidding_strategy: Mapped[str] = mapped_column(String(50), nullable=True)
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_draft: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    ad_groups = relationship("AdGroup", back_populates="campaign", lazy="selectin")
