"""V2-012: Add missing columns to integration_meta table

The table was created by create_all() from an older model version
that didn't have page_name, account_name, token_expires_at, etc.
v2_011 skipped because the table already existed.

Revision ID: v2_012
Revises: v2_011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "v2_012"
down_revision = "v2_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    cols = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'integration_meta'"
    ))
    existing = {row[0] for row in cols}

    if "page_name" not in existing:
        op.add_column("integration_meta", sa.Column("page_name", sa.String(255), nullable=True))
    if "account_name" not in existing:
        op.add_column("integration_meta", sa.Column("account_name", sa.String(255), nullable=True))
    if "token_expires_at" not in existing:
        op.add_column("integration_meta", sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True))
    if "is_active" not in existing:
        op.add_column("integration_meta", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    if "sync_error" not in existing:
        op.add_column("integration_meta", sa.Column("sync_error", sa.String(500), nullable=True))
    if "config_json" not in existing:
        op.add_column("integration_meta", sa.Column("config_json", JSONB, nullable=True))


def downgrade() -> None:
    for col in ["config_json", "sync_error", "is_active", "token_expires_at", "account_name", "page_name"]:
        try:
            op.drop_column("integration_meta", col)
        except Exception:
            pass
