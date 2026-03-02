import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # waste_control, coverage, messaging, bid_budget, targeting, structure, landing_page
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # low, medium, high
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)
    expected_impact_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    risk_level: Mapped[str] = mapped_column(String(10), default="low")
    action_diff_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected, applied, rolled_back
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
