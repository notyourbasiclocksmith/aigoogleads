import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, BigInteger, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    ad_group_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ad_groups.id", ondelete="CASCADE"), index=True)
    keyword_id: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="PHRASE")  # EXACT, PHRASE, BROAD
    status: Mapped[str] = mapped_column(String(20), default="ENABLED")
    cpc_bid_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    quality_score: Mapped[int] = mapped_column(Integer, nullable=True)
    labels_json: Mapped[dict] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    ad_group = relationship("AdGroup", back_populates="keywords")
