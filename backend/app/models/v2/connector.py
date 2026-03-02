import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # crm, slack_webhook, email, meta_ads, tiktok_ads, youtube_ads, generic_webhook
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="disconnected")  # disconnected, connected, error
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    events = relationship("ConnectorEvent", back_populates="connector", lazy="dynamic")
