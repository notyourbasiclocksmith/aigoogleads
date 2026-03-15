"""Google Business Profile Location model."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class GBPLocation(Base):
    __tablename__ = "gbp_locations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    # GBP API identifiers
    gbp_location_name: Mapped[str] = mapped_column(String(500), nullable=True, unique=True, index=True)  # e.g. "locations/12345"
    gbp_account_name: Mapped[str] = mapped_column(String(500), nullable=True)

    # Business info (synced from GBP)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=True)
    zip_code: Mapped[str] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(50), default="US")
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    website: Mapped[str] = mapped_column(String(500), nullable=True)
    latitude: Mapped[str] = mapped_column(String(50), nullable=True)
    longitude: Mapped[str] = mapped_column(String(50), nullable=True)
    primary_category: Mapped[str] = mapped_column(String(255), nullable=True)
    additional_categories_json: Mapped[dict] = mapped_column(JSONB, default=list)

    # Metrics (synced periodically)
    google_rating: Mapped[float] = mapped_column(Float, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)
    photos_count: Mapped[int] = mapped_column(Integer, nullable=True, default=0)

    # Auto-posting settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_post_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    post_frequency_days: Mapped[int] = mapped_column(Integer, default=3)

    last_post_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    posts = relationship("GBPPost", back_populates="location", cascade="all, delete-orphan")
