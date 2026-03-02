import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Learning(Base):
    __tablename__ = "learnings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)  # headline_theme, match_type, offer_type, negative_base
    pattern_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
