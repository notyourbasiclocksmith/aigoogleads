"""V2-010: Add Claude Operator chat tables

Revision ID: v2_010
Revises: v2_009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_010"
down_revision = "v2_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_conversations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("created_by", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "operator_messages",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=False), sa.ForeignKey("operator_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("structured_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "proposed_actions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=False), sa.ForeignKey("operator_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("message_id", UUID(as_uuid=False), sa.ForeignKey("operator_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("expected_impact", sa.String(500), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("action_payload", JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by", UUID(as_uuid=False), nullable=True),
    )

    op.create_table(
        "action_execution_logs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("proposed_action_id", UUID(as_uuid=False), sa.ForeignKey("proposed_actions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=False), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("request_payload", JSONB, nullable=True),
        sa.Column("response_payload", JSONB, nullable=True),
        sa.Column("before_state", JSONB, nullable=True),
        sa.Column("after_state", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("action_execution_logs")
    op.drop_table("proposed_actions")
    op.drop_table("operator_messages")
    op.drop_table("operator_conversations")
