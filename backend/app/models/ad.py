import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    ad_group_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ad_groups.id", ondelete="CASCADE"), index=True)
    ad_id: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    ad_type: Mapped[str] = mapped_column(String(30), default="RESPONSIVE_SEARCH_AD")
    headlines_json: Mapped[dict] = mapped_column(JSONB, default=list)
    descriptions_json: Mapped[dict] = mapped_column(JSONB, default=list)
    final_urls_json: Mapped[dict] = mapped_column(JSONB, default=list)
    assets_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    ad_group = relationship("AdGroup", back_populates="ads")
