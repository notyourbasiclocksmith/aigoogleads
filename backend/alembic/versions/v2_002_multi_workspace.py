"""V2-002: Multi-workspace, invitations, audit events, tenant settings, tenant slug

Revision ID: v2_002
Revises: v2_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_002"
down_revision = "v2_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Add slug to tenants ──
    op.add_column("tenants", sa.Column("slug", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_tenants_slug", "tenants", ["slug"])
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # ── user_sessions ──
    op.create_table(
        "user_sessions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active_tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("preferences_json", JSONB, server_default="{}"),
        sa.Column("last_tenant_switch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_active_tenant_id", "user_sessions", ["active_tenant_id"])

    # ── invitations ──
    op.create_table(
        "invitations",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("invited_by_user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])
    op.create_index("ix_invitations_token", "invitations", ["token"], unique=True)
    op.create_index("ix_invitations_email", "invitations", ["email"])

    # ── audit_events ──
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False, server_default="info"),
        sa.Column("metadata_json", JSONB, server_default="{}"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    # ── tenant_settings ──
    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("plan", sa.String(20), server_default="starter"),
        sa.Column("feature_flags_json", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Seed user_sessions for existing users ──
    op.execute("""
        INSERT INTO user_sessions (id, user_id, active_tenant_id, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            u.id,
            (SELECT tu.tenant_id FROM tenant_users tu WHERE tu.user_id = u.id LIMIT 1),
            NOW(),
            NOW()
        FROM users u
        WHERE NOT EXISTS (SELECT 1 FROM user_sessions us WHERE us.user_id = u.id)
    """)


def downgrade() -> None:
    op.drop_table("tenant_settings")
    op.drop_table("audit_events")
    op.drop_table("invitations")
    op.drop_table("user_sessions")
    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_constraint("uq_tenants_slug", "tenants")
    op.drop_column("tenants", "slug")
