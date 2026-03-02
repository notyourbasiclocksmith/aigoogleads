import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ChangeLog(Base):
    __tablename__ = "change_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)  # user, system
    actor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # campaign, ad_group, ad, keyword, negative, bid, budget
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    before_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    rollback_token: Mapped[str] = mapped_column(String(100), nullable=True, unique=True)
    is_rolled_back: Mapped[bool] = mapped_column(default=False)
