"""Module 1 — MCC / Agency Mode API Routes"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.v2.google_ads_accessible_account import GoogleAdsAccessibleAccount
from app.models.v2.tenant_google_ads_binding import TenantGoogleAdsBinding
from app.models.integration_google_ads import IntegrationGoogleAds

router = APIRouter()


class DiscoverAccountsRequest(BaseModel):
    tenant_id: str


class BindAccountRequest(BaseModel):
    tenant_id: str
    google_customer_id: str
    label: Optional[str] = None


class UnbindAccountRequest(BaseModel):
    tenant_id: str
    google_customer_id: str


class RollupKPIRequest(BaseModel):
    tenant_id: str
    range_days: int = 30


@router.post("/discover-accounts")
async def discover_accounts(req: DiscoverAccountsRequest, db: AsyncSession = Depends(get_db)):
    """Discover child accounts from MCC. In production, calls Google Ads API CustomerService."""
    stmt = select(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == req.tenant_id)
    result = await db.execute(stmt)
    integration = result.scalars().first()
    if not integration:
        raise HTTPException(404, "No Google Ads integration found for tenant")

    manager_id = integration.login_customer_id or getattr(integration, "manager_customer_id", None)
    if not manager_id:
        raise HTTPException(400, "No manager/login customer ID configured — not an MCC account")

    # Stub: In production, call Google Ads API list_accessible_customers
    mock_accounts = [
        {"customer_id": "1234567890", "descriptive_name": "Demo Account 1", "currency": "USD", "timezone": "America/Chicago", "status": "ENABLED"},
        {"customer_id": "0987654321", "descriptive_name": "Demo Account 2", "currency": "USD", "timezone": "America/New_York", "status": "ENABLED"},
    ]

    saved = []
    for acc in mock_accounts:
        existing = await db.execute(
            select(GoogleAdsAccessibleAccount).where(
                and_(
                    GoogleAdsAccessibleAccount.tenant_id == req.tenant_id,
                    GoogleAdsAccessibleAccount.customer_id == acc["customer_id"],
                )
            )
        )
        if existing.scalars().first():
            continue
        record = GoogleAdsAccessibleAccount(
            id=str(uuid.uuid4()),
            tenant_id=req.tenant_id,
            manager_customer_id=manager_id,
            customer_id=acc["customer_id"],
            descriptive_name=acc["descriptive_name"],
            currency=acc["currency"],
            timezone=acc["timezone"],
            status=acc["status"],
            last_seen_at=datetime.now(timezone.utc),
        )
        db.add(record)
        saved.append(acc)

    return {"discovered": len(saved), "accounts": saved}


@router.get("/accessible-accounts")
async def list_accessible_accounts(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(GoogleAdsAccessibleAccount).where(GoogleAdsAccessibleAccount.tenant_id == tenant_id)
    result = await db.execute(stmt)
    accounts = result.scalars().all()
    return [
        {
            "id": a.id, "customer_id": a.customer_id, "descriptive_name": a.descriptive_name,
            "currency": a.currency, "timezone": a.timezone, "status": a.status,
            "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
        }
        for a in accounts
    ]


@router.post("/bind-account")
async def bind_account(req: BindAccountRequest, db: AsyncSession = Depends(get_db)):
    """Bind a Google Ads customer account to a tenant."""
    existing = await db.execute(
        select(TenantGoogleAdsBinding).where(TenantGoogleAdsBinding.google_customer_id == req.google_customer_id)
    )
    if existing.scalars().first():
        raise HTTPException(409, "This customer account is already bound to a tenant")

    binding = TenantGoogleAdsBinding(
        id=str(uuid.uuid4()),
        tenant_id=req.tenant_id,
        google_customer_id=req.google_customer_id,
        label=req.label,
        enabled=True,
    )
    db.add(binding)
    return {"bound": True, "google_customer_id": req.google_customer_id}


@router.post("/unbind-account")
async def unbind_account(req: UnbindAccountRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(TenantGoogleAdsBinding).where(
        and_(
            TenantGoogleAdsBinding.tenant_id == req.tenant_id,
            TenantGoogleAdsBinding.google_customer_id == req.google_customer_id,
        )
    )
    result = await db.execute(stmt)
    binding = result.scalars().first()
    if not binding:
        raise HTTPException(404, "Binding not found")
    await db.delete(binding)
    return {"unbound": True}


@router.get("/bindings")
async def list_bindings(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(TenantGoogleAdsBinding).where(TenantGoogleAdsBinding.tenant_id == tenant_id)
    result = await db.execute(stmt)
    bindings = result.scalars().all()
    return [
        {"id": b.id, "google_customer_id": b.google_customer_id, "label": b.label, "enabled": b.enabled}
        for b in bindings
    ]


@router.get("/rollups/kpis")
async def rollup_kpis(tenant_id: str, range_days: int = 30, db: AsyncSession = Depends(get_db)):
    """Aggregate KPIs across all bound accounts. Stub — real impl queries performance_daily."""
    stmt = select(TenantGoogleAdsBinding).where(
        and_(TenantGoogleAdsBinding.tenant_id == tenant_id, TenantGoogleAdsBinding.enabled == True)
    )
    result = await db.execute(stmt)
    bindings = result.scalars().all()

    return {
        "tenant_id": tenant_id,
        "range_days": range_days,
        "accounts_count": len(bindings),
        "totals": {
            "impressions": 0, "clicks": 0, "cost_micros": 0,
            "conversions": 0, "conversion_value_micros": 0,
        },
        "note": "Stub — implement with actual performance_daily aggregation",
    }
