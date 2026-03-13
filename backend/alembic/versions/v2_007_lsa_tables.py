"""V2-007: Add LSA (Local Services Ads) tables — lsa_leads, lsa_conversations

Revision ID: v2_007
Revises: v2_006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_007"
down_revision = "v2_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── lsa_leads ──────────────────────────────────────────────────────
    op.create_table(
        "lsa_leads",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("google_customer_id", sa.String(20), nullable=False, index=True),
        sa.Column("lead_resource_name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("google_lead_id", sa.String(50), nullable=False, index=True),
        sa.Column("lead_type", sa.String(30), nullable=False),
        sa.Column("category_id", sa.String(50), nullable=True),
        sa.Column("service_id", sa.String(50), nullable=True),
        sa.Column("lead_status", sa.String(30), nullable=True),
        sa.Column("locale", sa.String(10), nullable=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("lead_charged", sa.Boolean, default=False),
        sa.Column("credit_state", sa.String(30), nullable=True),
        sa.Column("credit_state_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feedback_submitted", sa.Boolean, default=False),
        sa.Column("feedback_json", JSONB, nullable=True),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_sentiment", sa.String(20), nullable=True),
        sa.Column("ai_lead_quality_score", sa.Integer, nullable=True),
        sa.Column("ai_qualified_lead", sa.Boolean, nullable=True),
        sa.Column("ai_qualified_reason", sa.Text, nullable=True),
        sa.Column("ai_intents", JSONB, nullable=True),
        sa.Column("ai_action_items", JSONB, nullable=True),
        sa.Column("lead_creation_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── lsa_conversations ──────────────────────────────────────────────
    op.create_table(
        "lsa_conversations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("lead_id", UUID(as_uuid=False), sa.ForeignKey("lsa_leads.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conversation_resource_name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("participant_type", sa.String(30), nullable=True),
        sa.Column("event_datetime", sa.DateTime(timezone=True), nullable=True),
        sa.Column("call_duration_ms", sa.Integer, nullable=True),
        sa.Column("call_recording_url", sa.Text, nullable=True),
        sa.Column("message_text", sa.Text, nullable=True),
        sa.Column("attachment_urls", JSONB, nullable=True),
        sa.Column("transcription_text", sa.Text, nullable=True),
        sa.Column("transcription_status", sa.String(20), nullable=True),
        sa.Column("transcription_segments", JSONB, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("lsa_conversations")
    op.drop_table("lsa_leads")
