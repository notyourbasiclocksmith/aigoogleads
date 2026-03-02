import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SerpScan(Base):
    __tablename__ = "serp_scans"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    geo: Mapped[str] = mapped_column(String(100), nullable=True)
    device: Mapped[str] = mapped_column(String(20), default="desktop")
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    results_json: Mapped[dict] = mapped_column(JSONB, default=list)
    ads_json: Mapped[dict] = mapped_column(JSONB, default=list)
