"""
OptimizationLearning — action-level learning from autonomous optimization outcomes.
Tracks: pattern detected → action taken → result observed → confidence updated.
Over time, the system learns which actions work best for each pattern.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OptimizationLearning(Base):
    __tablename__ = "optimization_learnings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    # tenant_id = NULL means global learning (cross-tenant)

    # Pattern that was detected
    pattern: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # e.g. "keyword_cost_gt_100_zero_conversions", "ctr_drop_gt_30pct_14d", "budget_limited_healthy_cpa"
    pattern_detail_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {entity_type, threshold_values, metrics_at_detection}

    # Action that was taken
    action_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # Maps to RecType: PAUSE_KEYWORD, ADD_NEGATIVE_KEYWORD, LOWER_KEYWORD_BID, etc.
    action_detail_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {entity_id, entity_name, proposed_state, ...}

    # Result observed (filled by feedback loop)
    result: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    # improved, degraded, neutral, rolled_back, unknown
    result_detail_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {before_metrics, after_metrics, delta_pct, evaluation_window_days}

    # Confidence score — updated incrementally with each new observation
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    observation_count: Mapped[int] = mapped_column(Integer, default=1)

    # Linked artifacts
    cycle_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    recommendation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
