"""
Meta Ads (Facebook/Instagram) API Router.
Handles: OAuth flow, ad account selection, connection management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.config import settings
from app.core.deps import require_tenant, CurrentUser
from app.models.v2.integration_meta import IntegrationMeta

router = APIRouter()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OAUTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/oauth/authorize")
async def meta_authorize(
    user: CurrentUser = Depends(require_tenant),
    origin: str = Query("onboarding"),
):
    """Get Meta OAuth authorization URL."""
    from app.services.meta_oauth_service import get_authorization_url
    url = get_authorization_url(user.tenant_id, origin=origin)
    return {"auth_url": url, "authorization_url": url}


@router.get("/oauth/callback")
async def meta_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback from Facebook, store tokens."""
    from app.services.meta_oauth_service import exchange_code_for_tokens, discover_ad_accounts, discover_pages
    from app.core.security import decrypt_token

    parts = state.split(":")
    if len(parts) < 2 or parts[0] != "meta":
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    tenant_id = parts[1]
    result = await exchange_code_for_tokens(code, tenant_id, db)

    # Auto-discover ad accounts and pages
    try:
        conn_result = await db.execute(
            select(IntegrationMeta).where(IntegrationMeta.tenant_id == tenant_id)
        )
        conn = conn_result.scalar_one_or_none()
        if conn and conn.access_token_encrypted:
            token = decrypt_token(conn.access_token_encrypted)

            # Auto-select first ad account if only one
            ad_accounts = await discover_ad_accounts(token)
            if ad_accounts and len(ad_accounts) == 1:
                acct = ad_accounts[0]
                conn.ad_account_id = f"act_{acct.get('account_id', '')}"
                conn.account_name = acct.get("name") or acct.get("business_name") or "Meta Ad Account"

            # Auto-select first page
            pages = await discover_pages(token)
            if pages and len(pages) == 1:
                conn.page_id = pages[0].get("id")
                conn.page_name = pages[0].get("name")

            await db.flush()
    except Exception as e:
        import structlog
        structlog.get_logger().warning("Meta auto-discover failed", error=str(e), tenant_id=tenant_id)

    await db.commit()

    # Redirect to frontend
    frontend_url = settings.APP_URL
    origin = parts[2] if len(parts) > 2 else "onboarding"
    redirect_path = "/settings" if origin == "settings" else "/onboarding"
    return RedirectResponse(url=f"{frontend_url}{redirect_path}?meta=connected", status_code=302)


@router.get("/oauth/status")
async def meta_status(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Check if Meta Ads is connected for this tenant."""
    result = await db.execute(
        select(IntegrationMeta).where(IntegrationMeta.tenant_id == user.tenant_id)
    )
    conn = result.scalar_one_or_none()
    connected = bool(conn and conn.access_token_encrypted and conn.is_active)
    return {
        "connected": connected,
        "ad_account_id": conn.ad_account_id if conn else None,
        "account_name": conn.account_name if conn else None,
        "page_name": conn.page_name if conn else None,
        "sync_error": conn.sync_error if conn else None,
    }


@router.delete("/oauth/disconnect")
async def meta_disconnect(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect Meta Ads integration."""
    result = await db.execute(
        select(IntegrationMeta).where(IntegrationMeta.tenant_id == user.tenant_id)
    )
    conn = result.scalar_one_or_none()
    if conn:
        conn.is_active = False
        conn.access_token_encrypted = ""  # Empty string, not None (DB has NOT NULL constraint)
        conn.sync_error = None
        await db.commit()
    return {"status": "disconnected"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AD ACCOUNT MANAGEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/ad-accounts")
async def list_ad_accounts(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List discoverable Meta ad accounts."""
    from app.services.meta_oauth_service import get_valid_access_token, discover_ad_accounts
    token = await get_valid_access_token(user.tenant_id, db)
    if not token:
        raise HTTPException(status_code=400, detail="Meta not connected")
    accounts = await discover_ad_accounts(token)
    return {"ad_accounts": accounts}


@router.get("/pages")
async def list_pages(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List discoverable Facebook Pages."""
    from app.services.meta_oauth_service import get_valid_access_token, discover_pages
    token = await get_valid_access_token(user.tenant_id, db)
    if not token:
        raise HTTPException(status_code=400, detail="Meta not connected")
    pages = await discover_pages(token)
    return {"pages": pages}


class SelectAdAccountRequest(BaseModel):
    ad_account_id: str
    page_id: Optional[str] = None


@router.post("/ad-accounts/select")
async def select_ad_account(
    req: SelectAdAccountRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Select which Meta ad account (and optionally page) to manage."""
    from app.services.meta_oauth_service import get_valid_access_token, discover_ad_accounts, discover_pages

    result = await db.execute(
        select(IntegrationMeta).where(IntegrationMeta.tenant_id == user.tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn or not conn.is_active:
        raise HTTPException(status_code=400, detail="Meta not connected")

    token = await get_valid_access_token(user.tenant_id, db)
    if not token:
        raise HTTPException(status_code=400, detail="Meta token expired")

    # Validate the ad account exists
    accounts = await discover_ad_accounts(token)
    acct = next((a for a in accounts if f"act_{a.get('account_id')}" == req.ad_account_id), None)
    if not acct:
        raise HTTPException(status_code=404, detail="Ad account not found")

    conn.ad_account_id = req.ad_account_id
    conn.account_name = acct.get("name") or acct.get("business_name") or "Meta Ad Account"

    # Set page if provided
    if req.page_id:
        pages = await discover_pages(token)
        page = next((p for p in pages if p.get("id") == req.page_id), None)
        if page:
            conn.page_id = req.page_id
            conn.page_name = page.get("name")

    await db.commit()
    return {
        "success": True,
        "ad_account_id": conn.ad_account_id,
        "account_name": conn.account_name,
        "page_id": conn.page_id,
        "page_name": conn.page_name,
    }
