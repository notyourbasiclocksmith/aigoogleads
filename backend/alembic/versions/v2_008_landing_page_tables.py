"""V2-008: Add landing page tables — landing_pages, landing_page_variants,
landing_page_events, expansion_recommendations, ai_generation_logs

Revision ID: v2_008
Revises: v2_007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_008"
down_revision = "v2_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── landing_pages ────────────────────────────────────────────────
    op.create_table(
        "landing_pages",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("campaign_id", UUID(as_uuid=False), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("service", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("page_type", sa.String(30), server_default="service"),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("is_ai_generated", sa.Boolean, server_default="true"),
        sa.Column("strategy_json", JSONB, server_default="{}"),
        sa.Column("content_json", JSONB, server_default="{}"),
        sa.Column("style_json", JSONB, server_default="{}"),
        sa.Column("seo_json", JSONB, server_default="{}"),
        sa.Column("audit_score", sa.Float, nullable=True),
        sa.Column("audit_json", JSONB, server_default="{}"),
        sa.Column("last_audited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── landing_page_variants ────────────────────────────────────────
    op.create_table(
        "landing_page_variants",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("landing_page_id", UUID(as_uuid=False), sa.ForeignKey("landing_pages.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("variant_key", sa.String(20), nullable=False),
        sa.Column("variant_name", sa.String(100), nullable=False),
        sa.Column("content_json", JSONB, server_default="{}"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_winner", sa.Boolean, server_default="false"),
        sa.Column("visits", sa.Integer, server_default="0"),
        sa.Column("conversions", sa.Integer, server_default="0"),
        sa.Column("conversion_rate", sa.Float, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── landing_page_events ──────────────────────────────────────────
    op.create_table(
        "landing_page_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("landing_page_id", UUID(as_uuid=False), sa.ForeignKey("landing_pages.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("variant_id", UUID(as_uuid=False), nullable=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("gclid", sa.String(255), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(255), nullable=True),
        sa.Column("metadata_json", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── expansion_recommendations ────────────────────────────────────
    op.create_table(
        "expansion_recommendations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_campaign_id", UUID(as_uuid=False), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expansion_type", sa.String(30), nullable=False),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("score", sa.Float, server_default="0"),
        sa.Column("scoring_json", JSONB, server_default="{}"),
        sa.Column("campaign_prompt", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="suggested"),
        sa.Column("generated_campaign_id", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── ai_generation_logs ───────────────────────────────────────────
    op.create_table(
        "ai_generation_logs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("input_json", JSONB, server_default="{}"),
        sa.Column("output_json", JSONB, server_default="{}"),
        sa.Column("tokens_used", sa.Integer, server_default="0"),
        sa.Column("duration_ms", sa.Integer, server_default="0"),
        sa.Column("success", sa.Boolean, server_default="true"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_generation_logs")
    op.drop_table("expansion_recommendations")
    op.drop_table("landing_page_events")
    op.drop_table("landing_page_variants")
    op.drop_table("landing_pages")
