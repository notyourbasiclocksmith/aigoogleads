import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class CreativeAudit(Base):
    __tablename__ = "creative_audits"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("operator_scans.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # campaign, ad_group, ad
    entity_id: Mapped[str] = mapped_column(String(255), nullable=True)
    entity_name: Mapped[str] = mapped_column(String(500), nullable=True)

    copy_audit_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {strengths, weaknesses, missing_angles, cta_score, urgency_score, trust_score, specificity_score}
    asset_audit_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {sitelinks, callouts, snippets, images, missing_assets}
    image_prompt_pack_json: Mapped[dict] = mapped_column(JSONB, default=list)
    # [{prompt, category, aspect_ratio, placement, emotional_angle}]
    generated_creatives_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {headlines, descriptions, sitelinks, callouts, rsa_concepts}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    scan = relationship("OperatorScan", back_populates="creative_audits")
