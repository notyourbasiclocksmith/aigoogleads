import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True)
    website_url: Mapped[str] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    industry_classification: Mapped[str] = mapped_column(String(100), nullable=True)
    primary_conversion_goal: Mapped[str] = mapped_column(String(50), nullable=True)  # calls, forms, bookings
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    avg_ticket_estimate: Mapped[int] = mapped_column(default=0)
    services_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    locations_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    usp_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    brand_voice_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    offers_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    trust_signals_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    competitor_targets_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    constraints_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    snippets_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    gbp_link: Mapped[str] = mapped_column(String(500), nullable=True)

    # Structured business identity fields (populated from GBP or manual entry)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=True)
    zip_code: Mapped[str] = mapped_column(String(20), nullable=True)
    google_rating: Mapped[float] = mapped_column(Float, nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=True)
    years_experience: Mapped[int] = mapped_column(Integer, nullable=True)
    license_info: Mapped[str] = mapped_column(String(255), nullable=True)
    service_radius_miles: Mapped[int] = mapped_column(Integer, nullable=True)
    business_hours_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"monday": "8:00-18:00", ...}
    primary_category: Mapped[str] = mapped_column(String(255), nullable=True)  # from GBP
    gbp_place_id: Mapped[str] = mapped_column(String(255), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = relationship("Tenant", back_populates="business_profile")
