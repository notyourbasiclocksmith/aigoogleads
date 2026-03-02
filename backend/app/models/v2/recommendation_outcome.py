import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class RecommendationOutcome(Base):
    __tablename__ = "recommendation_outcomes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    recommendation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("recommendations.id", ondelete="CASCADE"), index=True)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)  # 7, 14, 30
    actual_metrics_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    delta_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    labeled_outcome: Mapped[str] = mapped_column(String(20), nullable=True)  # win, neutral, loss
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
