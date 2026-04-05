"""
IntegrationMeta — stores Meta Ads connection per tenant.
"""
from sqlalchemy import Column, String, DateTime, JSON, func
from app.core.database import Base


class IntegrationMeta(Base):
    __tablename__ = "integration_meta"

    id = Column(String(36), primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(String(36), nullable=False, unique=True, index=True)
    ad_account_id = Column(String(100), nullable=False)
    access_token_encrypted = Column(String(2000), nullable=False)
    page_id = Column(String(100), nullable=True)
    config_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
