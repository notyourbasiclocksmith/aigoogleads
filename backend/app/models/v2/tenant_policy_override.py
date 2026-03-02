import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TenantPolicyOverride(Base):
    __tablename__ = "tenant_policy_overrides"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("policy_rules.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
