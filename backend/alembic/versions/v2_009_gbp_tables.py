"""V2-009: Add Google Business Profile tables — gbp_connections, gbp_locations,
gbp_posts, gbp_post_templates, gbp_reviews + new columns on business_profiles

Revision ID: v2_009
Revises: v2_008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_009"
down_revision = "v2_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New columns on business_profiles ─────────────────────────────
    op.add_column("business_profiles", sa.Column("address", sa.String(500), nullable=True))
    op.add_column("business_profiles", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("business_profiles", sa.Column("state", sa.String(50), nullable=True))
    op.add_column("business_profiles", sa.Column("zip_code", sa.String(20), nullable=True))
    op.add_column("business_profiles", sa.Column("google_rating", sa.Float, nullable=True))
    op.add_column("business_profiles", sa.Column("review_count", sa.Integer, nullable=True))
    op.add_column("business_profiles", sa.Column("years_experience", sa.Integer, nullable=True))
    op.add_column("business_profiles", sa.Column("license_info", sa.String(255), nullable=True))
    op.add_column("business_profiles", sa.Column("service_radius_miles", sa.Integer, nullable=True))
    op.add_column("business_profiles", sa.Column("business_hours_json", JSONB, server_default="{}", nullable=True))
    op.add_column("business_profiles", sa.Column("primary_category", sa.String(255), nullable=True))
    op.add_column("business_profiles", sa.Column("gbp_place_id", sa.String(255), nullable=True))

    # ── gbp_connections ──────────────────────────────────────────────
    op.create_table(
        "gbp_connections",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True, nullable=False),
        sa.Column("account_id", sa.String(255), nullable=True),
        sa.Column("location_id", sa.String(255), nullable=True),
        sa.Column("location_name", sa.String(255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text, nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text, nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── gbp_locations ────────────────────────────────────────────────
    op.create_table(
        "gbp_locations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("gbp_location_name", sa.String(500), unique=True, index=True, nullable=True),
        sa.Column("gbp_account_name", sa.String(500), nullable=True),
        sa.Column("business_name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(50), server_default="US"),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("latitude", sa.String(50), nullable=True),
        sa.Column("longitude", sa.String(50), nullable=True),
        sa.Column("primary_category", sa.String(255), nullable=True),
        sa.Column("additional_categories_json", JSONB, server_default="[]"),
        sa.Column("google_rating", sa.Float, nullable=True),
        sa.Column("review_count", sa.Integer, default=0),
        sa.Column("photos_count", sa.Integer, default=0),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("auto_post_enabled", sa.Boolean, default=False),
        sa.Column("post_frequency_days", sa.Integer, default=3),
        sa.Column("last_post_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── gbp_posts ────────────────────────────────────────────────────
    op.create_table(
        "gbp_posts",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("location_id", UUID(as_uuid=False), sa.ForeignKey("gbp_locations.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("gbp_post_name", sa.String(500), unique=True, nullable=True),
        sa.Column("post_type", sa.String(20), default="UPDATE"),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("media_url", sa.Text, nullable=True),
        sa.Column("media_type", sa.String(50), nullable=True),
        sa.Column("call_to_action", sa.String(50), nullable=True),
        sa.Column("cta_url", sa.Text, nullable=True),
        sa.Column("city_mentions", JSONB, server_default="[]"),
        sa.Column("service_keywords", JSONB, server_default="[]"),
        sa.Column("event_title", sa.String(255), nullable=True),
        sa.Column("event_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer_coupon_code", sa.String(100), nullable=True),
        sa.Column("offer_terms", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), default="draft", index=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("views_count", sa.Integer, default=0),
        sa.Column("clicks_count", sa.Integer, default=0),
        sa.Column("calls_count", sa.Integer, default=0),
        sa.Column("direction_requests_count", sa.Integer, default=0),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),
        sa.Column("source_campaign_id", UUID(as_uuid=False), nullable=True),
        sa.Column("generation_model", sa.String(50), nullable=True),
        sa.Column("auto_generated", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── gbp_post_templates ───────────────────────────────────────────
    op.create_table(
        "gbp_post_templates",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("post_type", sa.String(20), default="UPDATE"),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("call_to_action", sa.String(50), nullable=True),
        sa.Column("include_emoji", sa.Boolean, default=True),
        sa.Column("include_utm_params", sa.Boolean, default=True),
        sa.Column("max_length", sa.Integer, default=300),
        sa.Column("tone", sa.String(50), default="professional"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── gbp_reviews ──────────────────────────────────────────────────
    op.create_table(
        "gbp_reviews",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("location_id", UUID(as_uuid=False), sa.ForeignKey("gbp_locations.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("gbp_review_name", sa.String(500), unique=True, nullable=True),
        sa.Column("reviewer_name", sa.String(255), nullable=True),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("review_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_owner_reply", sa.Boolean, default=False),
        sa.Column("owner_reply", sa.Text, nullable=True),
        sa.Column("owner_reply_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_generated_reply", sa.Text, nullable=True),
        sa.Column("ai_reply_approved", sa.Boolean, default=False),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("gbp_reviews")
    op.drop_table("gbp_post_templates")
    op.drop_table("gbp_posts")
    op.drop_table("gbp_locations")
    op.drop_table("gbp_connections")

    op.drop_column("business_profiles", "gbp_place_id")
    op.drop_column("business_profiles", "primary_category")
    op.drop_column("business_profiles", "business_hours_json")
    op.drop_column("business_profiles", "service_radius_miles")
    op.drop_column("business_profiles", "license_info")
    op.drop_column("business_profiles", "years_experience")
    op.drop_column("business_profiles", "review_count")
    op.drop_column("business_profiles", "google_rating")
    op.drop_column("business_profiles", "zip_code")
    op.drop_column("business_profiles", "state")
    op.drop_column("business_profiles", "city")
    op.drop_column("business_profiles", "address")
