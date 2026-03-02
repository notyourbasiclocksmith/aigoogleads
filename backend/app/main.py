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
