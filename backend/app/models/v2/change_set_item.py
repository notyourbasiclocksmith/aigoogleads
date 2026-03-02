import uuid
from sqlalchemy import Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ChangeSetItem(Base):
    __tablename__ = "change_set_items"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    change_set_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("change_sets.id", ondelete="CASCADE"), index=True)
    change_log_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("change_logs.id", ondelete="CASCADE"))
    apply_order: Mapped[int] = mapped_column(Integer, nullable=False)

    change_set = relationship("ChangeSet", back_populates="items")
