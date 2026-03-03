from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog

from app.core.config import settings
from app.api import auth, tenants, onboarding, dashboard, ads_accounts, ads_audit, ads_prompt, campaigns, creative, competitors, optimizations, experiments, reports, admin_settings
from app.api import workspace
from app.api.v2 import mcc, conversions, change_mgmt, connectors, policy, billing, notifications, evaluation

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Ignite Ads AI backend", env=settings.APP_ENV)
    # Run Alembic migrations on startup
    import subprocess, os
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            logger.info("Alembic migrations completed", stdout=result.stdout.strip())
        else:
            logger.error("Alembic migration failed", stderr=result.stderr.strip())
    except Exception as e:
        logger.error("Alembic migration error", error=str(e))
    yield
    logger.info("Shutting down Ignite Ads AI backend")


app = FastAPI(
    title="Ignite Ads AI",
    description="Multi-Tenant AI Google Ads Marketing Worker",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(workspace.router, prefix="/api", tags=["Workspace"])
app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
app.include_router(onboarding.router, prefix="/api/onboarding", tags=["Onboarding"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(ads_accounts.router, prefix="/api/ads/accounts", tags=["Ads Accounts"])
app.include_router(ads_audit.router, prefix="/api/ads/audit", tags=["Ads Audit"])
app.include_router(ads_prompt.router, prefix="/api/ads/prompt", tags=["Ads Prompt"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(creative.router, prefix="/api/creative", tags=["Creative"])
app.include_router(competitors.router, prefix="/api/intel/competitors", tags=["Competitors"])
app.include_router(optimizations.router, prefix="/api/optimizations", tags=["Optimizations"])
app.include_router(experiments.router, prefix="/api/experiments", tags=["Experiments"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(admin_settings.router, prefix="/api/settings", tags=["Settings"])

# V2 API Routes
app.include_router(mcc.router, prefix="/api/v2/mcc", tags=["V2 MCC/Agency"])
app.include_router(conversions.router, prefix="/api/v2/conversions", tags=["V2 Conversion Truth"])
app.include_router(change_mgmt.router, prefix="/api/v2/changes", tags=["V2 Change Management"])
app.include_router(connectors.router, prefix="/api/v2/connectors", tags=["V2 Connectors"])
app.include_router(policy.router, prefix="/api/v2/policy", tags=["V2 Policy Compliance"])
app.include_router(billing.router, prefix="/api/v2/billing", tags=["V2 Billing"])
app.include_router(notifications.router, prefix="/api/v2/notifications", tags=["V2 Notifications"])
app.include_router(evaluation.router, prefix="/api/v2/evaluation", tags=["V2 Evaluation"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/debug/tables")
async def debug_tables():
    from app.core.database import get_db
    from sqlalchemy import text
    async for db in get_db():
        result = await db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        tables = [row[0] for row in result]
        return {"tables": tables, "count": len(tables)}


@app.post("/api/debug/register")
async def debug_register():
    """Register admin user with full error reporting."""
    import traceback
    from app.core.database import async_session_factory
    from app.core.security import hash_password, create_access_token, create_refresh_token
    from app.models.user import User
    from sqlalchemy import select
    try:
        async with async_session_factory() as db:
            existing = await db.execute(select(User).where(User.email == "contact@thekeybot.com"))
            if existing.scalar_one_or_none():
                return {"status": "already_exists"}
            user = User(
                email="contact@thekeybot.com",
                password_hash=hash_password("Monte76140@!"),
                full_name="Admin",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            token = create_access_token(user_id=user.id)
            return {"status": "created", "user_id": user.id, "token": token}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}


@app.post("/api/debug/migrate")
async def debug_migrate():
    """Create all tables from SQLAlchemy metadata, then stamp alembic head."""
    import subprocess, os
    from sqlalchemy import create_engine
    from app.core.database import Base
    import app.models  # noqa: ensure all models loaded
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    # Stamp alembic so future migrations know we're at head
    result = subprocess.run(
        ["alembic", "stamp", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True, timeout=60
    )
    return {
        "tables_created": True,
        "alembic_stamp_rc": result.returncode,
        "alembic_stdout": result.stdout,
        "alembic_stderr": result.stderr,
    }
