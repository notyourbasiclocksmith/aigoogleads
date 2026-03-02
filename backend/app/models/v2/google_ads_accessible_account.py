import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class GoogleAdsAccessibleAccount(Base):
    __tablename__ = "google_ads_accessible_accounts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    manager_customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    descriptive_name: Mapped[str] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
