import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class OperatorScan(Base):
    __tablename__ = "operator_scans"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("integrations_google_ads.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    date_range_start: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    date_range_end: Mapped[str] = mapped_column(String(10), nullable=False)
    scan_goal: Mapped[str] = mapped_column(String(50), default="full_review")  # reduce_waste, increase_conversions, improve_cpa, scale_winners, full_review
    campaign_scope: Mapped[str] = mapped_column(String(20), default="all")  # all, selected
    campaign_ids_json: Mapped[dict] = mapped_column(JSONB, default=list)  # list of campaign IDs if scope=selected

    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    # queued, collecting_data, analyzing, generating_recommendations,
    # building_projections, running_creative_audit, ready, failed

    # Results
    summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # executive summary metrics
    metrics_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # raw collected metrics
    narrative_summary: Mapped[str] = mapped_column(Text, nullable=True)  # plain-English AI narrative
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    recommendations = relationship("OperatorRecommendation", back_populates="scan", lazy="selectin")
    creative_audits = relationship("CreativeAudit", back_populates="scan", lazy="selectin")
