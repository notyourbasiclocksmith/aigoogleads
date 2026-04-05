"""V2-015: Add mode column to operator_conversations

Track which connector (google_ads, meta_ads, gbp, image, auto) was used
for each conversation session.

Revision ID: v2_015
Revises: v2_014
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_015"
down_revision = "v2_014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "operator_conversations",
        sa.Column("mode", sa.String(30), nullable=True, server_default="auto"),
    )


def downgrade():
    op.drop_column("operator_conversations", "mode")
