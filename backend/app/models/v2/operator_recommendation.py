import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class OperatorRecommendation(Base):
    __tablename__ = "operator_recommendations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("operator_scans.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    # Classification
    recommendation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # PAUSE_KEYWORD, ADD_NEGATIVE_KEYWORD, LOWER_KEYWORD_BID, RAISE_KEYWORD_BID,
    # CREATE_AD_GROUP, SPLIT_AD_GROUP, CREATE_CAMPAIGN, PAUSE_AD, CREATE_AD_VARIANTS,
    # REWRITE_RSA, ADD_ASSETS, ADD_SITELINKS, ADD_CALLOUTS, INCREASE_BUDGET,
    # DECREASE_BUDGET, CHANGE_BIDDING_STRATEGY, ADD_LOCATION, EXCLUDE_LOCATION,
    # ADJUST_DEVICE_MODIFIER, ADD_AD_SCHEDULE_RULE, CREATE_EXPERIMENT,
    # RESTRUCTURE_THEME_CLUSTER, ADD_BRAND_SPECIFIC_CAMPAIGN, ADD_HIGH_INTENT_CAMPAIGN,
    # POLICY_FIX, IMAGE_REFRESH, CREATE_IMAGE_ASSET_PACK

    group_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # budget_bidding, keywords_search_terms, negative_keywords, campaign_structure,
    # ad_groups, ad_copy, creative_assets, device_modifiers, geo_targeting,
    # ad_schedule, audience_signals, extensions_assets, new_campaigns, policy_compliance

    # Entity references
    entity_type: Mapped[str] = mapped_column(String(30), nullable=True)  # campaign, ad_group, keyword, ad, asset
    entity_id: Mapped[str] = mapped_column(String(255), nullable=True)  # Google Ads resource ID
    entity_name: Mapped[str] = mapped_column(String(500), nullable=True)
    parent_entity_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # Content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    current_state_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    proposed_state_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Scoring
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    risk_level: Mapped[str] = mapped_column(String(10), default="low")  # low, medium, high
    impact_projection_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {spend_delta, click_delta, conversion_delta, cpa_delta, scenarios: {conservative, base, upside}}

    # Metadata
    generated_by: Mapped[str] = mapped_column(String(20), default="rule")  # rule, heuristic, llm, hybrid
    policy_flags_json: Mapped[dict] = mapped_column(JSONB, default=list)
    prerequisites_json: Mapped[dict] = mapped_column(JSONB, default=list)
    priority_order: Mapped[int] = mapped_column(Integer, default=100)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # pending, approved, rejected, applied, failed, rolled_back

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    scan = relationship("OperatorScan", back_populates="recommendations")
