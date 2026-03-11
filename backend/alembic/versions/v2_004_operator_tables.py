"""V2-004: Add AI Campaign Operator tables

Revision ID: v2_004
Revises: v2_003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_004"
down_revision = "v2_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── operator_scans ───────────────────────────────────────────────────
    op.create_table(
        "operator_scans",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_id", UUID(as_uuid=False), sa.ForeignKey("integrations_google_ads.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("requested_by", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("date_range_start", sa.String(10), nullable=False),
        sa.Column("date_range_end", sa.String(10), nullable=False),
        sa.Column("scan_goal", sa.String(50), server_default="full_review"),
        sa.Column("campaign_scope", sa.String(20), server_default="all"),
        sa.Column("campaign_ids_json", JSONB, server_default="[]"),
        sa.Column("status", sa.String(30), server_default="queued", index=True),
        sa.Column("summary_json", JSONB, server_default="{}"),
        sa.Column("metrics_snapshot_json", JSONB, server_default="{}"),
        sa.Column("narrative_summary", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("risk_score", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── operator_recommendations ─────────────────────────────────────────
    op.create_table(
        "operator_recommendations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=False), sa.ForeignKey("operator_scans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("recommendation_type", sa.String(60), nullable=False, index=True),
        sa.Column("group_name", sa.String(60), nullable=False, index=True),
        sa.Column("entity_type", sa.String(30), nullable=True),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("entity_name", sa.String(500), nullable=True),
        sa.Column("parent_entity_id", sa.String(255), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("evidence_json", JSONB, server_default="{}"),
        sa.Column("current_state_json", JSONB, server_default="{}"),
        sa.Column("proposed_state_json", JSONB, server_default="{}"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("risk_level", sa.String(10), server_default="low"),
        sa.Column("impact_projection_json", JSONB, server_default="{}"),
        sa.Column("generated_by", sa.String(20), server_default="rule"),
        sa.Column("policy_flags_json", JSONB, server_default="[]"),
        sa.Column("prerequisites_json", JSONB, server_default="[]"),
        sa.Column("priority_order", sa.Integer, server_default="100"),
        sa.Column("status", sa.String(20), server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── operator_change_sets ─────────────────────────────────────────────
    op.create_table(
        "operator_change_sets",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=False), sa.ForeignKey("operator_scans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_id", UUID(as_uuid=False), sa.ForeignKey("integrations_google_ads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft", index=True),
        sa.Column("selected_recommendation_ids", JSONB, server_default="[]"),
        sa.Column("edited_overrides_json", JSONB, server_default="{}"),
        sa.Column("projection_summary_json", JSONB, server_default="{}"),
        sa.Column("validation_result_json", JSONB, server_default="{}"),
        sa.Column("apply_summary_json", JSONB, server_default="{}"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── operator_mutations ───────────────────────────────────────────────
    op.create_table(
        "operator_mutations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("change_set_id", UUID(as_uuid=False), sa.ForeignKey("operator_change_sets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("recommendation_id", UUID(as_uuid=False), sa.ForeignKey("operator_recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mutation_type", sa.String(60), nullable=False),
        sa.Column("google_ads_resource", sa.String(500), nullable=True),
        sa.Column("request_payload_json", JSONB, server_default="{}"),
        sa.Column("response_payload_json", JSONB, server_default="{}"),
        sa.Column("before_snapshot_json", JSONB, server_default="{}"),
        sa.Column("after_snapshot_json", JSONB, server_default="{}"),
        sa.Column("reversible", sa.Boolean, server_default="true"),
        sa.Column("rollback_payload_json", JSONB, server_default="{}"),
        sa.Column("status", sa.String(20), server_default="pending", index=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("apply_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── creative_audits ──────────────────────────────────────────────────
    op.create_table(
        "creative_audits",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("scan_id", UUID(as_uuid=False), sa.ForeignKey("operator_scans.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("entity_name", sa.String(500), nullable=True),
        sa.Column("copy_audit_json", JSONB, server_default="{}"),
        sa.Column("asset_audit_json", JSONB, server_default="{}"),
        sa.Column("image_prompt_pack_json", JSONB, server_default="[]"),
        sa.Column("generated_creatives_json", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("creative_audits")
    op.drop_table("operator_mutations")
    op.drop_table("operator_change_sets")
    op.drop_table("operator_recommendations")
    op.drop_table("operator_scans")
