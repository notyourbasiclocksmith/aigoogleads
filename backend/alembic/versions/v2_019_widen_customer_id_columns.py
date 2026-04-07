"""Widen customer_id columns from VARCHAR(20) to VARCHAR(50).

Meta Ads conversations use customer_id = 'meta_{tenant_uuid}' which is 41 chars,
exceeding the original VARCHAR(20) limit.

Revision ID: v2_019
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_019"
down_revision = "v2_018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "operator_conversations",
        "customer_id",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )
    op.alter_column(
        "action_execution_logs",
        "customer_id",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "action_execution_logs",
        "customer_id",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
    op.alter_column(
        "operator_conversations",
        "customer_id",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
