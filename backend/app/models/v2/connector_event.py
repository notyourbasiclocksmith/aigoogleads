import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ConnectorEvent(Base):
    __tablename__ = "connector_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"))
    connector_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("connectors.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)  # info, warning, error
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    connector = relationship("Connector", back_populates="events")
