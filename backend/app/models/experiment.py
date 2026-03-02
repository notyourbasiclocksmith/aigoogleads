import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    entity_scope_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    variants_json: Mapped[dict] = mapped_column(JSONB, default=list)
    success_metric: Mapped[str] = mapped_column(String(50), default="ctr")  # ctr, conversions, cpa, roas
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, running, paused, completed
    results_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
