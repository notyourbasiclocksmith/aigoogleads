import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PolicyScanResult(Base):
    __tablename__ = "policy_scan_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ad, headline, description, extension
    entity_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    warnings_json: Mapped[dict] = mapped_column(JSONB, default=list)
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
