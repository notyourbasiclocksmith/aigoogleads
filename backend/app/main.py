from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog

from app.core.config import settings
from app.api import auth, tenants, onboarding, dashboard, ads_accounts, ads_audit, ads_prompt, ads_data, campaigns, creative, competitors, optimizations, experiments, reports, admin_settings, lsa, bridge, gbp, meta, brain
from app.api import workspace, brain_analytics, brain_gbp, brain_meta, brain_image
from app.api import operator, operator_meta, operator_unified
from app.api.v2 import mcc, conversions, change_mgmt, connectors, policy, billing, notifications, evaluation, operator as operator_v2, growth, strategist

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting IntelliAds AI backend", env=settings.APP_ENV)

    # 1. Ensure all tables exist (create_all is safe — won't drop/alter existing)
    try:
        from sqlalchemy import create_engine
        from app.core.database import Base
        import app.models  # noqa: F401 — trigger model registration
        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        sync_engine = create_engine(sync_url, pool_pre_ping=True)
        Base.metadata.create_all(sync_engine)
        sync_engine.dispose()
        logger.info("Database tables verified (create_all)")
    except Exception as e:
        logger.error("create_all failed", error=str(e))

    # 2. Run Alembic migrations on startup
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
    logger.info("Shutting down IntelliAds AI backend")


app = FastAPI(
    title="IntelliAds AI",
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
app.include_router(ads_data.router, prefix="/api/ads", tags=["Ads Data"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(creative.router, prefix="/api/creative", tags=["Creative"])
app.include_router(competitors.router, prefix="/api/intel/competitors", tags=["Competitors"])
app.include_router(optimizations.router, prefix="/api/optimizations", tags=["Optimizations"])
app.include_router(experiments.router, prefix="/api/experiments", tags=["Experiments"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(admin_settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(lsa.router, prefix="/api/lsa", tags=["LSA (Local Services Ads)"])
app.include_router(bridge.router, prefix="/api/bridge", tags=["Bridge (CallFlux ↔ IntelliAds)"])
app.include_router(gbp.router, prefix="/api/gbp", tags=["Google Business Profile"])
app.include_router(meta.router, prefix="/api/meta", tags=["Meta Ads (Facebook/Instagram)"])
app.include_router(operator.router, prefix="/api/operator", tags=["Claude Operator"])
app.include_router(operator_meta.router, prefix="/api/operator/meta", tags=["Claude Meta Operator"])
app.include_router(operator_unified.router, prefix="/api/operator/unified", tags=["Unified Auto Operator"])

# Brain API (S2S for Jarvis)
app.include_router(brain.router, prefix="/api/v1/brain", tags=["Brain API"])
app.include_router(brain_analytics.router, prefix="/api/v1/brain", tags=["Brain Analytics"])
app.include_router(brain_gbp.router, prefix="/api/v1/brain", tags=["Brain GBP"])
app.include_router(brain_meta.router, prefix="/api/v1/brain", tags=["Brain Meta Ads"])
app.include_router(brain_image.router, prefix="/api/v1/brain", tags=["Brain Images"])

# V2 API Routes
app.include_router(mcc.router, prefix="/api/v2/mcc", tags=["V2 MCC/Agency"])
app.include_router(conversions.router, prefix="/api/v2/conversions", tags=["V2 Conversion Truth"])
app.include_router(change_mgmt.router, prefix="/api/v2/changes", tags=["V2 Change Management"])
app.include_router(connectors.router, prefix="/api/v2/connectors", tags=["V2 Connectors"])
app.include_router(policy.router, prefix="/api/v2/policy", tags=["V2 Policy Compliance"])
app.include_router(billing.router, prefix="/api/v2/billing", tags=["V2 Billing"])
app.include_router(notifications.router, prefix="/api/v2/notifications", tags=["V2 Notifications"])
app.include_router(evaluation.router, prefix="/api/v2/evaluation", tags=["V2 Evaluation"])
app.include_router(operator_v2.router, prefix="/api/v2/operator", tags=["V2 AI Operator"])
app.include_router(growth.router, prefix="/api/v2/growth", tags=["V2 Growth Features"])
app.include_router(strategist.router, prefix="/api/v2/strategist", tags=["V2 Campaign Strategist AI"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


# Global exception handler for expired Google Ads tokens
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from app.integrations.google_ads.oauth import OAuthTokenExpiredError
    if isinstance(exc, OAuthTokenExpiredError):
        return JSONResponse(
            status_code=401,
            content={
                "detail": str(exc),
                "error_code": "GOOGLE_ADS_TOKEN_EXPIRED",
                "action": "reconnect",
            },
        )
    # Re-raise all other exceptions to default handler
    raise exc
