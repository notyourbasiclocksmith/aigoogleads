"""
One-time script to ensure ALL tables exist on the production database.
Run this after deploy if migrations haven't created base tables.

Usage:
  DATABASE_URL=postgresql://... python ensure_tables.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from app.core.database import Base
from app.models import *  # noqa: F401, F403

DB_URL = os.environ.get("DATABASE_URL", "")
if not DB_URL:
    print("ERROR: Set DATABASE_URL environment variable")
    sys.exit(1)

# Convert async URL to sync if needed
DB_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")

print(f"Connecting to: {DB_URL[:50]}...")
engine = create_engine(DB_URL)

# Check existing tables
with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
    ))
    existing = [r[0] for r in result]
    print(f"\nExisting tables ({len(existing)}): {', '.join(existing[:10])}{'...' if len(existing) > 10 else ''}")

# Create all missing tables (will NOT drop or alter existing ones)
Base.metadata.create_all(engine)

# Verify
with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
    ))
    after = [r[0] for r in result]
    new_tables = set(after) - set(existing)
    print(f"\nAfter create_all: {len(after)} tables total")
    if new_tables:
        print(f"NEW tables created ({len(new_tables)}): {', '.join(sorted(new_tables))}")
    else:
        print("No new tables needed — all tables already exist.")

    # Ensure alembic_version is stamped
    result = conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='alembic_version')"
    ))
    has_alembic = result.scalar()
    if has_alembic:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        ver = result.scalar()
        print(f"Alembic version: {ver}")
    else:
        print("No alembic_version table — creating and stamping v2_009")
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('v2_009')"))
        conn.commit()

engine.dispose()
print("\nDone!")
