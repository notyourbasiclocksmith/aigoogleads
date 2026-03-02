import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class IntegrationGA4(Base):
    __tablename__ = "integrations_ga4"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    property_id: Mapped[str] = mapped_column(String(50), nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(String(1024), nullable=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
