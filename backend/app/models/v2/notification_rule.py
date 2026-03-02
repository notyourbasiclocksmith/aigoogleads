import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class NotificationRule(Base):
    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=True)
    min_severity: Mapped[str] = mapped_column(String(20), default="warning")
    quiet_start_hour: Mapped[int] = mapped_column(Integer, nullable=True)
    quiet_end_hour: Mapped[int] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
