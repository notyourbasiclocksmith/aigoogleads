"""V2-005: Add ads data pipeline tables (search terms, keyword/ad/ad-group perf, landing pages, recommendations)

Revision ID: v2_005
Revises: v2_004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_005"
down_revision = "v2_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── search_term_performance ───────────────────────────────────────
    op.create_table(
        "search_term_performance",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("campaign_id", sa.String(30), nullable=False, index=True),
        sa.Column("ad_group_id", sa.String(30), nullable=False, index=True),
        sa.Column("keyword_id", sa.String(30), nullable=True),
        sa.Column("keyword_text", sa.String(500), nullable=True),
        sa.Column("search_term", sa.String(500), nullable=False),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("impressions", sa.Integer, server_default="0"),
        sa.Column("clicks", sa.Integer, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, server_default="0"),
        sa.Column("conversions", sa.Float, server_default="0"),
        sa.Column("conversion_value", sa.Float, server_default="0"),
        sa.Column("ctr", sa.Float, server_default="0"),
        sa.Column("average_cpc_micros", sa.BigInteger, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── keyword_performance_daily ─────────────────────────────────────
    op.create_table(
        "keyword_performance_daily",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("campaign_id", sa.String(30), nullable=False, index=True),
        sa.Column("ad_group_id", sa.String(30), nullable=False, index=True),
        sa.Column("keyword_id", sa.String(30), nullable=False, index=True),
        sa.Column("keyword_text", sa.String(500), nullable=True),
        sa.Column("match_type", sa.String(20), nullable=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("impressions", sa.Integer, server_default="0"),
        sa.Column("clicks", sa.Integer, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, server_default="0"),
        sa.Column("conversions", sa.Float, server_default="0"),
        sa.Column("conversion_value", sa.Float, server_default="0"),
        sa.Column("ctr", sa.Float, server_default="0"),
        sa.Column("average_cpc_micros", sa.BigInteger, server_default="0"),
        sa.Column("quality_score", sa.Integer, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── ad_performance_daily ──────────────────────────────────────────
    op.create_table(
        "ad_performance_daily",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("campaign_id", sa.String(30), nullable=False, index=True),
        sa.Column("ad_group_id", sa.String(30), nullable=False, index=True),
        sa.Column("ad_id", sa.String(30), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("impressions", sa.Integer, server_default="0"),
        sa.Column("clicks", sa.Integer, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, server_default="0"),
        sa.Column("conversions", sa.Float, server_default="0"),
        sa.Column("conversion_value", sa.Float, server_default="0"),
        sa.Column("ctr", sa.Float, server_default="0"),
        sa.Column("average_cpc_micros", sa.BigInteger, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── ad_group_performance_daily ────────────────────────────────────
    op.create_table(
        "ad_group_performance_daily",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("campaign_id", sa.String(30), nullable=False, index=True),
        sa.Column("ad_group_id", sa.String(30), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("impressions", sa.Integer, server_default="0"),
        sa.Column("clicks", sa.Integer, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, server_default="0"),
        sa.Column("conversions", sa.Float, server_default="0"),
        sa.Column("conversion_value", sa.Float, server_default="0"),
        sa.Column("ctr", sa.Float, server_default="0"),
        sa.Column("average_cpc_micros", sa.BigInteger, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── landing_page_performance ──────────────────────────────────────
    op.create_table(
        "landing_page_performance",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("campaign_id", sa.String(30), nullable=False, index=True),
        sa.Column("ad_group_id", sa.String(30), nullable=True),
        sa.Column("landing_page_url", sa.String(2048), nullable=False),
        sa.Column("date", sa.Date, nullable=False, index=True),
        sa.Column("impressions", sa.Integer, server_default="0"),
        sa.Column("clicks", sa.Integer, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, server_default="0"),
        sa.Column("conversions", sa.Float, server_default="0"),
        sa.Column("conversion_value", sa.Float, server_default="0"),
        sa.Column("mobile_friendly_click_rate", sa.Float, nullable=True),
        sa.Column("speed_score", sa.Float, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── google_recommendations ────────────────────────────────────────
    op.create_table(
        "google_recommendations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("recommendation_resource_name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("type", sa.String(100), nullable=False, index=True),
        sa.Column("campaign_id", sa.String(30), nullable=True, index=True),
        sa.Column("campaign_name", sa.String(255), nullable=True),
        sa.Column("ad_group_id", sa.String(30), nullable=True),
        sa.Column("impact_base_metrics", JSONB, server_default="{}"),
        sa.Column("impact_potential_metrics", JSONB, server_default="{}"),
        sa.Column("details", JSONB, server_default="{}"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("google_recommendations")
    op.drop_table("landing_page_performance")
    op.drop_table("ad_group_performance_daily")
    op.drop_table("ad_performance_daily")
    op.drop_table("keyword_performance_daily")
    op.drop_table("search_term_performance")
