import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Chicago")
    autonomy_mode: Mapped[str] = mapped_column(String(20), default="suggest")  # suggest, semi_auto, full_auto
    risk_tolerance: Mapped[str] = mapped_column(String(20), default="low")  # low, medium, high
    daily_budget_cap_micros: Mapped[int] = mapped_column(default=0)
    weekly_change_cap_pct: Mapped[int] = mapped_column(default=15)
    tier: Mapped[str] = mapped_column(String(20), default="starter")  # starter, pro, elite
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    users = relationship("TenantUser", back_populates="tenant", lazy="selectin")
    business_profile = relationship("BusinessProfile", back_populates="tenant", uselist=False, lazy="selectin")
    integrations = relationship("IntegrationGoogleAds", back_populates="tenant", lazy="selectin")
    gbp_connection = relationship("GBPConnection", back_populates="tenant", uselist=False, lazy="selectin")
