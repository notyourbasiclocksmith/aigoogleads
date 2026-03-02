import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Negative(Base):
    __tablename__ = "negatives"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(20), default="campaign")  # campaign, ad_group, account
    campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    ad_group_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ad_groups.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="EXACT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
