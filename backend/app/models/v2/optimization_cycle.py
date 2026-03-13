"""
OptimizationCycle — tracks each autonomous optimization run.
One cycle = snapshot → detect → recommend → risk-filter → execute → monitor.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OptimizationCycle(Base):
    __tablename__ = "optimization_cycles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("integrations_google_ads.id", ondelete="CASCADE"), index=True)

    # Trigger
    trigger: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled, manual, alert

    # Lifecycle
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    # running, completed, completed_no_actions, failed, skipped

    # Snapshot summary
    snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {total_spend, total_conversions, total_clicks, campaigns, keywords, search_terms, ...}

    # Detection results
    problems_detected: Mapped[int] = mapped_column(Integer, default=0)
    problems_json: Mapped[dict] = mapped_column(JSONB, default=list)
    # [{type, entity, severity, description}, ...]

    # Actions generated → filtered → executed
    actions_generated: Mapped[int] = mapped_column(Integer, default=0)
    actions_approved: Mapped[int] = mapped_column(Integer, default=0)
    actions_executed: Mapped[int] = mapped_column(Integer, default=0)
    actions_blocked: Mapped[int] = mapped_column(Integer, default=0)
    actions_json: Mapped[dict] = mapped_column(JSONB, default=list)
    # [{action_type, entity_type, entity_id, risk_level, status, impact_estimate}, ...]

    # Impact projection
    projected_monthly_savings: Mapped[float] = mapped_column(Float, default=0.0)
    projected_conversion_lift: Mapped[float] = mapped_column(Float, default=0.0)

    # Linked operator artifacts
    scan_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)  # OperatorScan if created
    change_set_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)  # OperatorChangeSet if created

    # Feedback (filled 24h later by feedback_loop)
    feedback_status: Mapped[str] = mapped_column(String(20), nullable=True)
    # pending_review, improved, degraded, neutral, rolled_back
    feedback_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {before_metrics, after_metrics, delta, verdict}
    feedback_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
