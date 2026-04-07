import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class LandingPage(Base):
    __tablename__ = "landing_pages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    service: Mapped[str] = mapped_column(String(255), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft, preview, published, paused, archived, suspended
    page_type: Mapped[str] = mapped_column(String(30), default="service")  # service, offer, emergency, brand, generic
    url: Mapped[str] = mapped_column(Text, nullable=True)  # external URL if using existing page
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    # AI generation metadata
    strategy_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # offer angle, tone, CTA strategy
    content_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # hero, sections, CTAs, trust signals
    style_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # colors, fonts, layout
    seo_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # title, meta, schema markup
    # Audit scores
    audit_score: Mapped[float] = mapped_column(Float, nullable=True)
    audit_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # detailed audit breakdown
    last_audited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    variants = relationship("LandingPageVariant", back_populates="landing_page", lazy="selectin")


class LandingPageVariant(Base):
    __tablename__ = "landing_page_variants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    landing_page_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("landing_pages.id", ondelete="CASCADE"), index=True)
    variant_key: Mapped[str] = mapped_column(String(20), nullable=False)  # A, B, C
    variant_name: Mapped[str] = mapped_column(String(100), nullable=False)  # Emergency, Savings, Expert
    content_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # full page content for this variant
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    # Metrics
    visits: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    conversion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    landing_page = relationship("LandingPage", back_populates="variants")


class LandingPageEvent(Base):
    __tablename__ = "landing_page_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    landing_page_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("landing_pages.id", ondelete="CASCADE"), nullable=True, index=True)
    variant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)  # visit, call_click, form_submit, cta_click, scroll_depth
    gclid: Mapped[str] = mapped_column(String(255), nullable=True)
    utm_source: Mapped[str] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # scroll %, device, referrer, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ExpansionRecommendation(Base):
    __tablename__ = "expansion_recommendations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    source_campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    expansion_type: Mapped[str] = mapped_column(String(30), nullable=False)  # make_expansion, service_expansion, location_expansion
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    scoring_json: Mapped[dict] = mapped_column(JSONB, default=dict)  # relevance, intent, demand, competition breakdown
    campaign_prompt: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested, accepted, generated, dismissed
    generated_campaign_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AIGenerationLog(Base):
    __tablename__ = "ai_generation_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)  # campaign_builder, landing_page, page_auditor, expansion_planner, etc.
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # generate, audit, expand, score
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
