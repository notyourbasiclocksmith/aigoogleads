"""V2-006: Add autonomous optimization engine tables (optimization_cycles, optimization_learnings)

Revision ID: v2_006
Revises: v2_005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_006"
down_revision = "v2_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── optimization_cycles ────────────────────────────────────────────
    op.create_table(
        "optimization_cycles",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("account_id", UUID(as_uuid=False), sa.ForeignKey("integrations_google_ads.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("trigger", sa.String(20), server_default="scheduled"),
        sa.Column("status", sa.String(30), server_default="running", index=True),
        sa.Column("snapshot_json", JSONB, server_default="{}"),
        sa.Column("problems_detected", sa.Integer, server_default="0"),
        sa.Column("problems_json", JSONB, server_default="[]"),
        sa.Column("actions_generated", sa.Integer, server_default="0"),
        sa.Column("actions_approved", sa.Integer, server_default="0"),
        sa.Column("actions_executed", sa.Integer, server_default="0"),
        sa.Column("actions_blocked", sa.Integer, server_default="0"),
        sa.Column("actions_json", JSONB, server_default="[]"),
        sa.Column("projected_monthly_savings", sa.Float, server_default="0"),
        sa.Column("projected_conversion_lift", sa.Float, server_default="0"),
        sa.Column("scan_id", UUID(as_uuid=False), nullable=True),
        sa.Column("change_set_id", UUID(as_uuid=False), nullable=True),
        sa.Column("feedback_status", sa.String(20), nullable=True),
        sa.Column("feedback_json", JSONB, server_default="{}"),
        sa.Column("feedback_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── optimization_learnings ─────────────────────────────────────────
    op.create_table(
        "optimization_learnings",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("pattern", sa.String(200), nullable=False, index=True),
        sa.Column("pattern_detail_json", JSONB, server_default="{}"),
        sa.Column("action_type", sa.String(60), nullable=False, index=True),
        sa.Column("action_detail_json", JSONB, server_default="{}"),
        sa.Column("result", sa.String(30), nullable=True, index=True),
        sa.Column("result_detail_json", JSONB, server_default="{}"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("observation_count", sa.Integer, server_default="1"),
        sa.Column("cycle_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("recommendation_id", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("optimization_learnings")
    op.drop_table("optimization_cycles")
