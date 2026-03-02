import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AdGroup(Base):
    __tablename__ = "ad_groups"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    ad_group_id: Mapped[str] = mapped_column(String(30), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENABLED")
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    campaign = relationship("Campaign", back_populates="ad_groups")
    ads = relationship("Ad", back_populates="ad_group", lazy="selectin")
    keywords = relationship("Keyword", back_populates="ad_group", lazy="selectin")
