"""
IntegrationMeta — stores Meta Ads (Facebook/Instagram) connection per tenant.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class IntegrationMeta(Base):
    __tablename__ = "integration_meta"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    ad_account_id = Column(String(100), nullable=True)  # e.g. "act_123456"
    access_token_encrypted = Column(String(2000), nullable=True)
    page_id = Column(String(100), nullable=True)
    page_name = Column(String(255), nullable=True)
    account_name = Column(String(255), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sync_error = Column(String(500), nullable=True)
    config_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
