import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)  # IMAGE, VIDEO, HEADLINE, DESCRIPTION, SITELINK, CALLOUT, LOGO
    source: Mapped[str] = mapped_column(String(30), default="manual")  # manual, seopix, google_ads, generated
    url: Mapped[str] = mapped_column(String(2048), nullable=True)
    content: Mapped[str] = mapped_column(String(2048), nullable=True)
    seopix_job_id: Mapped[str] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
