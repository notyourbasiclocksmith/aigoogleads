"""
LSA Lead model — stores Google Local Services Ads leads (calls, messages, bookings).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class LSALead(Base):
    __tablename__ = "lsa_leads"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    google_customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Google's lead resource name (e.g. "customers/123/localServicesLeads/456")
    lead_resource_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    google_lead_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Lead details
    lead_type: Mapped[str] = mapped_column(String(30), nullable=False)  # PHONE_CALL, MESSAGE, BOOKING
    category_id: Mapped[str] = mapped_column(String(50), nullable=True)  # Service category
    service_id: Mapped[str] = mapped_column(String(50), nullable=True)  # Specific service type
    lead_status: Mapped[str] = mapped_column(String(30), nullable=True)  # NEW, ACTIVE, BOOKED, DECLINED, EXPIRED, WIPED_OUT
    locale: Mapped[str] = mapped_column(String(10), nullable=True)

    # Contact info (may be wiped by Google after retention period)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=True)

    # Billing
    lead_charged: Mapped[bool] = mapped_column(Boolean, default=False)  # Did Google charge for this?
    credit_state: Mapped[str] = mapped_column(String(30), nullable=True)  # PENDING, CREDITED, NOT_CREDITED
    credit_state_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Dispute / feedback
    feedback_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_json: Mapped[dict] = mapped_column(JSONB, nullable=True)  # Our feedback submission details

    # AI enrichment (Phase 4 — filled when recording is processed)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)
    ai_sentiment: Mapped[str] = mapped_column(String(20), nullable=True)
    ai_lead_quality_score: Mapped[int] = mapped_column(nullable=True)
    ai_qualified_lead: Mapped[bool] = mapped_column(Boolean, nullable=True)
    ai_qualified_reason: Mapped[str] = mapped_column(Text, nullable=True)
    ai_intents: Mapped[dict] = mapped_column(JSONB, nullable=True)
    ai_action_items: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Timestamps
    lead_creation_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    conversations = relationship("LSAConversation", back_populates="lead", cascade="all, delete-orphan", lazy="selectin")
