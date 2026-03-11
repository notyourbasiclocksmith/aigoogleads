import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class OperatorChangeSet(Base):
    __tablename__ = "operator_change_sets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("operator_scans.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("integrations_google_ads.id", ondelete="CASCADE"))
    approved_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # draft, validating, validated, applying, applied, partially_applied, failed, rolled_back

    selected_recommendation_ids: Mapped[dict] = mapped_column(JSONB, default=list)
    edited_overrides_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # user edits before apply
    projection_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    validation_result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    apply_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    mutations = relationship("OperatorMutation", back_populates="change_set", lazy="selectin")
