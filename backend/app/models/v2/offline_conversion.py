import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OfflineConversion(Base):
    __tablename__ = "offline_conversions"
    __table_args__ = (UniqueConstraint("gclid", "conversion_name", "conversion_time", name="uq_offline_conv_dedup"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    gclid: Mapped[str] = mapped_column(String(255), nullable=False)
    conversion_name: Mapped[str] = mapped_column(String(255), nullable=False)
    conversion_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, uploaded, failed
    upload_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
