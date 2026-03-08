"""V2-003: Add sync progress tracking columns to integrations_google_ads

Revision ID: v2_003
Revises: v2_002
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_003"
down_revision = "v2_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integrations_google_ads", sa.Column("sync_status", sa.String(20), server_default="idle"))
    op.add_column("integrations_google_ads", sa.Column("sync_message", sa.String(500), nullable=True))
    op.add_column("integrations_google_ads", sa.Column("sync_progress", sa.Integer(), server_default="0"))
    op.add_column("integrations_google_ads", sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integrations_google_ads", sa.Column("sync_error", sa.String(1000), nullable=True))
    op.add_column("integrations_google_ads", sa.Column("campaigns_synced", sa.Integer(), server_default="0"))
    op.add_column("integrations_google_ads", sa.Column("conversions_synced", sa.Integer(), server_default="0"))


def downgrade() -> None:
    op.drop_column("integrations_google_ads", "conversions_synced")
    op.drop_column("integrations_google_ads", "campaigns_synced")
    op.drop_column("integrations_google_ads", "sync_error")
    op.drop_column("integrations_google_ads", "sync_started_at")
    op.drop_column("integrations_google_ads", "sync_progress")
    op.drop_column("integrations_google_ads", "sync_message")
    op.drop_column("integrations_google_ads", "sync_status")
