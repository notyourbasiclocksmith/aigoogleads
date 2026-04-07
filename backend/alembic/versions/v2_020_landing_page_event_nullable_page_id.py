"""Make landing_page_events.landing_page_id nullable.

FormsAI webhook leads may not have a landing_page_id yet,
so we need to allow NULL for form_submit events from webhooks.

Revision ID: v2_020
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "v2_020"
down_revision = "v2_019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "landing_page_events",
        "landing_page_id",
        existing_type=UUID(as_uuid=False),
        nullable=True,
    )


def downgrade() -> None:
    # Delete orphan events first
    op.execute("DELETE FROM landing_page_events WHERE landing_page_id IS NULL")
    op.alter_column(
        "landing_page_events",
        "landing_page_id",
        existing_type=UUID(as_uuid=False),
        nullable=False,
    )
