from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, require_owner, CurrentUser
from app.core.security import encrypt_token, decrypt_token
from app.models.integration_google_ads import IntegrationGoogleAds

router = APIRouter()


class ConnectAccountRequest(BaseModel):
    auth_code: str
    customer_id: str
    login_customer_id: Optional[str] = None


@router.get("")
async def list_accounts(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == user.tenant_id)
    )
    accounts = result.scalars().all()
    return [
        {
            "id": a.id,
            "customer_id": a.customer_id,
            "account_name": a.account_name,
            "is_active": a.is_active,
            "health_score": a.health_score,
            "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in accounts
    ]


@router.post("/connect")
async def connect_account(
    req: ConnectAccountRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    from app.integrations.google_ads.oauth import exchange_code_for_tokens
    tokens = await exchange_code_for_tokens(req.auth_code)
    if not tokens or "refresh_token" not in tokens:
        raise HTTPException(status_code=400, detail="Failed to exchange auth code for tokens")

    integration = IntegrationGoogleAds(
        tenant_id=user.tenant_id,
        customer_id=req.customer_id,
        login_customer_id=req.login_customer_id,
        refresh_token_encrypted=encrypt_token(tokens["refresh_token"]),
        access_token_cache=tokens.get("access_token"),
        account_name=f"Account {req.customer_id}",
    )
    db.add(integration)
    await db.flush()

    # Trigger initial sync
    from app.jobs.tasks import sync_ads_account_task
    sync_ads_account_task.delay(user.tenant_id, integration.id)

    return {"id": integration.id, "customer_id": req.customer_id, "status": "connected"}


@router.delete("/{account_id}")
async def disconnect_account(
    account_id: str,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.id == account_id,
            IntegrationGoogleAds.tenant_id == user.tenant_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.is_active = False
    await db.flush()
    return {"status": "disconnected"}


@router.post("/{account_id}/sync")
async def trigger_sync(
    account_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.id == account_id,
            IntegrationGoogleAds.tenant_id == user.tenant_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from app.jobs.tasks import sync_ads_account_task
    sync_ads_account_task.delay(user.tenant_id, account.id)

    return {"status": "sync_triggered"}
