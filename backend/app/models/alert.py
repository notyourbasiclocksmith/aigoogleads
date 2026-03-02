import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # budget_pacing, tracking_broken, ctr_drop, cpa_spike, search_term_leak, geo_waste
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low, medium, high, critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_ref_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
