"""One-time script to run v2_008 migration against production DB."""
try:
    import psycopg
    DB_URL = "postgresql://aigoogleads_user:RBV2NjnnuxQj42yYqbdqqqA7GMZ8hBrh@dpg-d6j0p9lm5p6s73cuithg-a.oregon-postgres.render.com/aigoogleads_db?sslmode=require"
    conn = psycopg.connect(DB_URL)
except ImportError:
    import psycopg2
    DB_URL = "postgresql://aigoogleads_user:RBV2NjnnuxQj42yYqbdqqqA7GMZ8hBrh@dpg-d6j0p9lm5p6s73cuithg-a.oregon-postgres.render.com/aigoogleads_db?sslmode=require"
    conn = psycopg2.connect(DB_URL)
conn.autocommit = False
cur = conn.cursor()

# Check existing tables
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema='public' 
    AND table_name IN ('landing_pages','landing_page_variants','landing_page_events',
                       'expansion_recommendations','ai_generation_logs','alembic_version')
""")
existing = [r[0] for r in cur.fetchall()]
print("Existing tables:", existing)

# Check alembic version
if 'alembic_version' in existing:
    cur.execute("SELECT version_num FROM alembic_version")
    ver = cur.fetchone()
    print("Current alembic version:", ver)

tables_to_create = []

if 'landing_pages' not in existing:
    tables_to_create.append('landing_pages')
    cur.execute("""
        CREATE TABLE landing_pages (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(255) NOT NULL UNIQUE,
            service VARCHAR(255),
            location VARCHAR(255),
            status VARCHAR(20) DEFAULT 'draft',
            page_type VARCHAR(30) DEFAULT 'service',
            url TEXT,
            is_ai_generated BOOLEAN DEFAULT true,
            strategy_json JSONB DEFAULT '{}',
            content_json JSONB DEFAULT '{}',
            style_json JSONB DEFAULT '{}',
            seo_json JSONB DEFAULT '{}',
            audit_score FLOAT,
            audit_json JSONB DEFAULT '{}',
            last_audited_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            published_at TIMESTAMPTZ
        )
    """)
    cur.execute("CREATE INDEX ix_landing_pages_tenant_id ON landing_pages(tenant_id)")
    cur.execute("CREATE INDEX ix_landing_pages_campaign_id ON landing_pages(campaign_id)")
    cur.execute("CREATE INDEX ix_landing_pages_slug ON landing_pages(slug)")
    print("Created: landing_pages")

if 'landing_page_variants' not in existing:
    tables_to_create.append('landing_page_variants')
    cur.execute("""
        CREATE TABLE landing_page_variants (
            id UUID PRIMARY KEY,
            landing_page_id UUID NOT NULL REFERENCES landing_pages(id) ON DELETE CASCADE,
            variant_key VARCHAR(20) NOT NULL,
            variant_name VARCHAR(100) NOT NULL,
            content_json JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT true,
            is_winner BOOLEAN DEFAULT false,
            visits INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            conversion_rate FLOAT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX ix_landing_page_variants_lp_id ON landing_page_variants(landing_page_id)")
    print("Created: landing_page_variants")

if 'landing_page_events' not in existing:
    tables_to_create.append('landing_page_events')
    cur.execute("""
        CREATE TABLE landing_page_events (
            id UUID PRIMARY KEY,
            landing_page_id UUID NOT NULL REFERENCES landing_pages(id) ON DELETE CASCADE,
            variant_id UUID,
            event_type VARCHAR(30) NOT NULL,
            gclid VARCHAR(255),
            utm_source VARCHAR(100),
            utm_medium VARCHAR(100),
            utm_campaign VARCHAR(255),
            metadata_json JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX ix_landing_page_events_lp_id ON landing_page_events(landing_page_id)")
    print("Created: landing_page_events")

if 'expansion_recommendations' not in existing:
    tables_to_create.append('expansion_recommendations')
    cur.execute("""
        CREATE TABLE expansion_recommendations (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            source_campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,
            expansion_type VARCHAR(30) NOT NULL,
            service_name VARCHAR(255) NOT NULL,
            score FLOAT DEFAULT 0,
            scoring_json JSONB DEFAULT '{}',
            campaign_prompt TEXT,
            status VARCHAR(20) DEFAULT 'suggested',
            generated_campaign_id UUID,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX ix_expansion_recs_tenant_id ON expansion_recommendations(tenant_id)")
    print("Created: expansion_recommendations")

if 'ai_generation_logs' not in existing:
    tables_to_create.append('ai_generation_logs')
    cur.execute("""
        CREATE TABLE ai_generation_logs (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            agent_name VARCHAR(50) NOT NULL,
            action VARCHAR(50) NOT NULL,
            input_json JSONB DEFAULT '{}',
            output_json JSONB DEFAULT '{}',
            tokens_used INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            success BOOLEAN DEFAULT true,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX ix_ai_gen_logs_tenant_id ON ai_generation_logs(tenant_id)")
    print("Created: ai_generation_logs")

# Update alembic version
if tables_to_create:
    cur.execute("UPDATE alembic_version SET version_num = 'v2_008'")
    print("Updated alembic_version to v2_008")

conn.commit()
print(f"\nDone! Created {len(tables_to_create)} tables: {tables_to_create}")
cur.close()
conn.close()
