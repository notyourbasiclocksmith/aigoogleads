import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class GoogleRecommendation(Base):
    __tablename__ = "google_recommendations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    recommendation_resource_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=True)
    ad_group_id: Mapped[str] = mapped_column(String(30), nullable=True)
    impact_base_metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    impact_potential_metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, applied, dismissed
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
