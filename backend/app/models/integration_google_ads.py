import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, BigInteger, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class IntegrationGoogleAds(Base):
    __tablename__ = "integrations_google_ads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    login_customer_id: Mapped[str] = mapped_column(String(20), nullable=True)
    refresh_token_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    access_token_cache: Mapped[str] = mapped_column(String(2048), nullable=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    developer_token_ref: Mapped[str] = mapped_column(String(255), nullable=True)
    account_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    health_score: Mapped[int] = mapped_column(default=0)
    sync_status: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")  # idle, syncing, completed, failed
    sync_message: Mapped[str] = mapped_column(String(500), nullable=True)
    sync_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 0-100
    sync_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_error: Mapped[str] = mapped_column(String(1000), nullable=True)
    campaigns_synced: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    conversions_synced: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", back_populates="integrations")
