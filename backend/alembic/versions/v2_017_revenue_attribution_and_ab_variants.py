"""V2-017: Add revenue_attributions and pipeline_ab_variants tables

revenue_attributions: IntelliDrive chain — Keyword → Click → Call → Job → Invoice → Revenue
pipeline_ab_variants: Tracks which pipeline prompt variants produce better campaigns

Revision ID: v2_017
Revises: v2_016
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2_017"
down_revision = "v2_016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Revenue Attributions ──────────────────────────────────
    op.create_table(
        "revenue_attributions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        # Google Ads linkage
        sa.Column("campaign_id", sa.String(50), nullable=True, index=True),
        sa.Column("ad_group_id", sa.String(50), nullable=True),
        sa.Column("keyword_text", sa.String(255), nullable=True, index=True),
        sa.Column("keyword_id", sa.String(50), nullable=True),
        sa.Column("click_id", sa.String(255), nullable=True),
        # Conversion event
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        # Lead details
        sa.Column("caller_phone", sa.String(30), nullable=True),
        sa.Column("lead_name", sa.String(255), nullable=True),
        sa.Column("lead_email", sa.String(255), nullable=True),
        # Job / invoice
        sa.Column("job_id", sa.String(100), nullable=True, index=True),
        sa.Column("job_type", sa.String(100), nullable=True),
        sa.Column("invoice_amount_cents", sa.Integer, nullable=True),
        sa.Column("invoice_date", sa.Date, nullable=True),
        sa.Column("revenue_confirmed", sa.Boolean, default=False),
        # Ad cost
        sa.Column("cost_micros", sa.BigInteger, nullable=True),
        # Notes
        sa.Column("notes", sa.Text, nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Pipeline A/B Variants ─────────────────────────────────
    op.create_table(
        "pipeline_ab_variants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("campaign_id", sa.String(255), nullable=True, index=True),
        sa.Column("variant_config", postgresql.JSONB, nullable=False),
        sa.Column("qa_score", sa.Float, nullable=False),
        sa.Column("real_ctr", sa.Float, nullable=True),
        sa.Column("real_conversions", sa.Integer, nullable=True),
        sa.Column("real_roas", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("performance_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pipeline_ab_variants")
    op.drop_table("revenue_attributions")
