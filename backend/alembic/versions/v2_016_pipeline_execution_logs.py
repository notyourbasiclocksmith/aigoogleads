"""V2-016: Add pipeline_execution_logs table

Tracks every pipeline, budget scaler, A/B generator, and audit run
for developer/analyst review per campaign.

Revision ID: v2_016
Revises: v2_015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2_016"
down_revision = "v2_015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipeline_execution_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("customer_id", sa.String(20), nullable=True),
        sa.Column("campaign_id", sa.String(30), nullable=True, index=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("service_type", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("input_summary", postgresql.JSONB, nullable=True),
        sa.Column("agent_results", postgresql.JSONB, nullable=True),
        sa.Column("ahrefs_data", postgresql.JSONB, nullable=True),
        sa.Column("output_summary", postgresql.JSONB, nullable=True),
        sa.Column("output_full", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("total_cost_cents", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("pipeline_execution_logs")
