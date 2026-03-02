import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Playbook(Base):
    __tablename__ = "playbooks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    industry: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)  # calls, forms, bookings, revenue
    template_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
