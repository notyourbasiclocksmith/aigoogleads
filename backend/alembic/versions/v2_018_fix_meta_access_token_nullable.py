"""V2-018: Make integration_meta.access_token_encrypted nullable

The model defines it as nullable=True but the DB constraint may be NOT NULL
from an older create_all(). The disconnect endpoint sets it to None which
triggers IntegrityError.

Revision ID: v2_018
Revises: v2_017
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_018"
down_revision = "v2_017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT is_nullable FROM information_schema.columns
        WHERE table_name = 'integration_meta' AND column_name = 'access_token_encrypted'
    """))
    row = result.fetchone()
    if row and row[0] == 'NO':
        op.alter_column('integration_meta', 'access_token_encrypted',
                        existing_type=sa.String(2000),
                        nullable=True)


def downgrade() -> None:
    pass
