import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AdsAccountCache(Base):
    __tablename__ = "ads_accounts_cache"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    account_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
