"""V2-013: Fix integration_meta column types — varchar to UUID

The table was created by create_all() from an older model that used
String for id/tenant_id. The current model uses UUID(as_uuid=False).

Revision ID: v2_013
Revises: v2_012
"""
from alembic import op
import sqlalchemy as sa

revision = "v2_013"
down_revision = "v2_012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if tenant_id is varchar (needs conversion to uuid)
    result = conn.execute(sa.text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'integration_meta' AND column_name = 'tenant_id'
    """))
    row = result.fetchone()
    if row and row[0] == 'character varying':
        # Drop FK constraint first if exists
        conn.execute(sa.text("""
            DO $$ BEGIN
                ALTER TABLE integration_meta DROP CONSTRAINT IF EXISTS integration_meta_tenant_id_fkey;
            EXCEPTION WHEN undefined_object THEN NULL;
            END $$;
        """))
        # Convert columns
        op.alter_column('integration_meta', 'tenant_id',
                        type_=sa.dialects.postgresql.UUID(as_uuid=False),
                        postgresql_using='tenant_id::uuid')
        # Re-add FK
        op.create_foreign_key(
            'integration_meta_tenant_id_fkey',
            'integration_meta', 'tenants',
            ['tenant_id'], ['id'],
            ondelete='CASCADE'
        )

    # Fix id column too
    result2 = conn.execute(sa.text("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'integration_meta' AND column_name = 'id'
    """))
    row2 = result2.fetchone()
    if row2 and row2[0] == 'character varying':
        op.alter_column('integration_meta', 'id',
                        type_=sa.dialects.postgresql.UUID(as_uuid=False),
                        postgresql_using='id::uuid',
                        server_default=sa.text('gen_random_uuid()'))


def downgrade() -> None:
    pass
