"""V2-011: Add Meta Ads integration table

Revision ID: v2_011
Revises: v2_010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_011"
down_revision = "v2_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_meta",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("ad_account_id", sa.String(100), nullable=True),
        sa.Column("access_token_encrypted", sa.String(2000), nullable=True),
        sa.Column("page_id", sa.String(100), nullable=True),
        sa.Column("page_name", sa.String(255), nullable=True),
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_error", sa.String(500), nullable=True),
        sa.Column("config_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("integration_meta")
