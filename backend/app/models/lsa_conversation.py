"""
LSA Conversation model — stores call/message details for LSA leads.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class LSAConversation(Base):
    __tablename__ = "lsa_conversations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    lead_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("lsa_leads.id", ondelete="CASCADE"), index=True)

    # Google's conversation resource name
    conversation_resource_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Conversation details
    channel: Mapped[str] = mapped_column(String(30), nullable=False)  # PHONE_CALL, MESSAGE
    participant_type: Mapped[str] = mapped_column(String(30), nullable=True)  # ADVERTISER, CONSUMER
    event_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Phone call details
    call_duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)  # Duration in milliseconds
    call_recording_url: Mapped[str] = mapped_column(Text, nullable=True)  # Google's recording URL

    # Message details
    message_text: Mapped[str] = mapped_column(Text, nullable=True)
    attachment_urls: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Transcription (Phase 4 — filled when recording is processed via CallFlux)
    transcription_text: Mapped[str] = mapped_column(Text, nullable=True)
    transcription_status: Mapped[str] = mapped_column(String(20), nullable=True)  # pending, processing, succeeded, failed
    transcription_segments: Mapped[dict] = mapped_column(JSONB, nullable=True)  # Word-level segments

    # Timestamps
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    lead = relationship("LSALead", back_populates="conversations")
