"""Add CallFlux call tracking fields to tenants table.

Each tenant maps to a CallFlux tenant for call tracking.
Stores CallFlux tenant ID, JWT tokens, and encrypted credentials.

Revision ID: v2_021
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_021"
down_revision = "v2_020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("callflux_tenant_id", sa.String(50), nullable=True))
    op.add_column("tenants", sa.Column("callflux_access_token", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("callflux_refresh_token", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("callflux_email", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("callflux_password_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "callflux_password_encrypted")
    op.drop_column("tenants", "callflux_email")
    op.drop_column("tenants", "callflux_refresh_token")
    op.drop_column("tenants", "callflux_access_token")
    op.drop_column("tenants", "callflux_tenant_id")
