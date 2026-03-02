import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SocialProfile(Base):
    __tablename__ = "social_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # facebook, instagram, tiktok, youtube, yelp
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    extracted_bio: Mapped[str] = mapped_column(Text, nullable=True)
    extracted_posts_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
