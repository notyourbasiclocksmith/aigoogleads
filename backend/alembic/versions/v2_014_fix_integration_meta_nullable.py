"""V2-014: Make integration_meta.ad_account_id nullable

The column was created as NOT NULL by an older create_all(), but OAuth
callback inserts a row before the user selects an ad account.

Revision ID: v2_014
Revises: v2_013
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_014"
down_revision = "v2_013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Check if the column is currently NOT NULL
    result = conn.execute(sa.text("""
        SELECT is_nullable FROM information_schema.columns
        WHERE table_name = 'integration_meta' AND column_name = 'ad_account_id'
    """))
    row = result.fetchone()
    if row and row[0] == 'NO':
        op.alter_column('integration_meta', 'ad_account_id',
                        existing_type=sa.String(100),
                        nullable=True)


def downgrade() -> None:
    pass
