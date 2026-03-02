import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Conversion(Base):
    __tablename__ = "conversions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(30), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=True)  # WEBPAGE, PHONE_CALL, IMPORT, etc.
    status: Mapped[str] = mapped_column(String(20), default="ENABLED")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
