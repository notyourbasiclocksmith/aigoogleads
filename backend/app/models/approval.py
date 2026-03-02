import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=True)
    change_log_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("change_logs.id", ondelete="SET NULL"), nullable=True)
    requested_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    approved_by: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, approved, rejected
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
