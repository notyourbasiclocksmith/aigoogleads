"""Google Business Profile Post model."""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Boolean, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class GBPPostStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class GBPPostType(str, enum.Enum):
    UPDATE = "UPDATE"
    EVENT = "EVENT"
    OFFER = "OFFER"
    PRODUCT = "PRODUCT"


class GBPPost(Base):
    __tablename__ = "gbp_posts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("gbp_locations.id", ondelete="CASCADE"), index=True)

    # GBP API reference
    gbp_post_name: Mapped[str] = mapped_column(String(500), nullable=True, unique=True)  # GBP resource name

    # Content
    post_type: Mapped[str] = mapped_column(SQLEnum(GBPPostType), default=GBPPostType.UPDATE)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)  # Main content (90-1500 chars)
    media_url: Mapped[str] = mapped_column(Text, nullable=True)
    media_type: Mapped[str] = mapped_column(String(50), nullable=True)  # IMAGE, VIDEO

    # CTA
    call_to_action: Mapped[str] = mapped_column(String(50), nullable=True)  # LEARN_MORE, CALL, BOOK
    cta_url: Mapped[str] = mapped_column(Text, nullable=True)

    # GEO optimization
    city_mentions: Mapped[dict] = mapped_column(JSONB, default=list)
    service_keywords: Mapped[dict] = mapped_column(JSONB, default=list)

    # Event-specific
    event_title: Mapped[str] = mapped_column(String(255), nullable=True)
    event_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    event_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Offer-specific
    offer_coupon_code: Mapped[str] = mapped_column(String(100), nullable=True)
    offer_terms: Mapped[str] = mapped_column(Text, nullable=True)

    # Scheduling
    status: Mapped[str] = mapped_column(SQLEnum(GBPPostStatus), default=GBPPostStatus.DRAFT, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Analytics
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    clicks_count: Mapped[int] = mapped_column(Integer, default=0)
    calls_count: Mapped[int] = mapped_column(Integer, default=0)
    direction_requests_count: Mapped[int] = mapped_column(Integer, default=0)

    # Error handling
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # AI generation metadata
    source_campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    generation_model: Mapped[str] = mapped_column(String(50), nullable=True)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    location = relationship("GBPLocation", back_populates="posts")


class GBPPostTemplate(Base):
    __tablename__ = "gbp_post_templates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    post_type: Mapped[str] = mapped_column(SQLEnum(GBPPostType), default=GBPPostType.UPDATE)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)  # supports {{city}}, {{service}} placeholders
    call_to_action: Mapped[str] = mapped_column(String(50), nullable=True)

    # Settings
    include_emoji: Mapped[bool] = mapped_column(Boolean, default=True)
    include_utm_params: Mapped[bool] = mapped_column(Boolean, default=True)
    max_length: Mapped[int] = mapped_column(Integer, default=300)
    tone: Mapped[str] = mapped_column(String(50), default="professional")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GBPReview(Base):
    """Synced reviews from GBP for monitoring and AI response generation."""
    __tablename__ = "gbp_reviews"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    location_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("gbp_locations.id", ondelete="CASCADE"), index=True)

    # GBP review data
    gbp_review_name: Mapped[str] = mapped_column(String(500), nullable=True, unique=True)
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    review_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Response
    has_owner_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_reply: Mapped[str] = mapped_column(Text, nullable=True)
    owner_reply_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_generated_reply: Mapped[str] = mapped_column(Text, nullable=True)
    ai_reply_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    # Sentiment
    sentiment: Mapped[str] = mapped_column(String(20), nullable=True)  # positive, neutral, negative

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    location = relationship("GBPLocation")
