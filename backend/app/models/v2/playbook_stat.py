import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PlaybookStat(Base):
    __tablename__ = "playbook_stats"
    __table_args__ = (UniqueConstraint("industry", "metric_key", name="uq_playbook_stat"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    stat_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
