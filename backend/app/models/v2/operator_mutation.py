import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class OperatorMutation(Base):
    __tablename__ = "operator_mutations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    change_set_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("operator_change_sets.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("operator_recommendations.id", ondelete="SET NULL"), nullable=True)

    mutation_type: Mapped[str] = mapped_column(String(60), nullable=False)
    google_ads_resource: Mapped[str] = mapped_column(String(500), nullable=True)
    request_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    response_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    before_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    rollback_payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending, applying, success, failed, rolled_back
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    apply_order: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    change_set = relationship("OperatorChangeSet", back_populates="mutations")
