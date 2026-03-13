from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from pydantic import BaseModel
from typing import Optional
import structlog

from app.core.config import settings
from app.core.database import get_db, async_session_factory
from app.core.deps import require_tenant, require_owner, CurrentUser
from app.core.security import encrypt_token, decrypt_token
from app.models.integration_google_ads import IntegrationGoogleAds

logger = structlog.get_logger()

router = APIRouter()


class ConnectAccountRequest(BaseModel):
    auth_code: str
    customer_id: str
    login_customer_id: Optional[str] = None


class SelectCustomerRequest(BaseModel):
    customer_id: str
    account_name: Optional[str] = None
    login_customer_id: Optional[str] = None


class SyncRequest(BaseModel):
    login_customer_id: Optional[str] = None


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(None),
    state: str = Query(""),
    error: str = Query(None),
):
    """Handle Google OAuth redirect after user authorizes."""
    frontend_url = settings.APP_URL.rstrip("/")

    if error or not code:
        logger.warning("OAuth callback error", error=error)
        return RedirectResponse(url=f"{frontend_url}/onboarding?oauth_error={error or 'no_code'}")

    # state = "tenant_id:user_id"
    parts = state.split(":")
    if len(parts) != 2:
        return RedirectResponse(url=f"{frontend_url}/onboarding?oauth_error=invalid_state")

    tenant_id, user_id = parts

    from app.integrations.google_ads.oauth import exchange_code_for_tokens
    tokens = await exchange_code_for_tokens(code)

    if not tokens or not tokens.get("refresh_token"):
        logger.error("Failed to exchange OAuth code for tokens")
        return RedirectResponse(url=f"{frontend_url}/onboarding?oauth_error=token_exchange_failed")

    # Reuse existing pending integration if one exists (avoid duplicates from repeated OAuth)
    async with async_session_factory() as db:
        existing_result = await db.execute(
            select(IntegrationGoogleAds).where(
                and_(
                    IntegrationGoogleAds.tenant_id == tenant_id,
                    IntegrationGoogleAds.customer_id == "pending",
                    IntegrationGoogleAds.is_active == True,
                )
            ).order_by(IntegrationGoogleAds.created_at.desc()).limit(1)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update existing pending integration with fresh tokens
            existing.refresh_token_encrypted = encrypt_token(tokens["refresh_token"])
            existing.access_token_cache = tokens.get("access_token")
            logger.info("Updated existing pending integration", tenant_id=tenant_id, integration_id=existing.id)
        else:
            integration = IntegrationGoogleAds(
                tenant_id=tenant_id,
                customer_id="pending",
                refresh_token_encrypted=encrypt_token(tokens["refresh_token"]),
                access_token_cache=tokens.get("access_token"),
                account_name="Google Ads (pending setup)",
            )
            db.add(integration)
            logger.info("Google Ads OAuth connected (new)", tenant_id=tenant_id)

        await db.commit()

    return RedirectResponse(url=f"{frontend_url}/onboarding?oauth_success=true")


@router.get("")
async def list_accounts(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.tenant_id == user.tenant_id,
                IntegrationGoogleAds.is_active == True,
            )
        )
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
            "sync_status": getattr(a, "sync_status", "idle") or "idle",
            "sync_message": getattr(a, "sync_message", None),
            "sync_progress": getattr(a, "sync_progress", 0) or 0,
            "campaigns_synced": getattr(a, "campaigns_synced", 0) or 0,
            "conversions_synced": getattr(a, "conversions_synced", 0) or 0,
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

    await db.delete(account)
    await db.flush()
    return {"status": "disconnected"}


@router.post("/reconnect-oauth")
async def reconnect_oauth(
    user: CurrentUser = Depends(require_tenant),
):
    """Generate a fresh OAuth URL so the user can re-authorize Google Ads."""
    from app.integrations.google_ads.oauth import get_oauth_url
    url = get_oauth_url(state=f"{user.tenant_id}:{user.user_id}")
    return {"oauth_url": url}


@router.get("/accessible-customers")
async def list_accessible_customers(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Use the stored OAuth refresh token to call Google Ads ListAccessibleCustomers,
    then fetch each customer's descriptive name.
    Returns a list of {customer_id, name, is_manager, currency, timezone}.
    """
    # Find the newest integration for this tenant (pending or otherwise) that has a refresh token
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.tenant_id == user.tenant_id,
                IntegrationGoogleAds.is_active == True,
            )
        ).order_by(IntegrationGoogleAds.created_at.desc()).limit(1)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="No Google Ads connection found. Please connect first.")

    try:
        refresh_token = decrypt_token(integration.refresh_token_encrypted)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to decrypt stored credentials. Please reconnect Google Ads.")

    # Use the google-ads library to list accessible customers
    try:
        from google.ads.googleads.client import GoogleAdsClient as GAdsClient

        credentials = {
            "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
            "client_id": settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "use_proto_plus": True,
        }
        gads_client = GAdsClient.load_from_dict(credentials)
        customer_service = gads_client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()

        accessible = []
        ga_service = gads_client.get_service("GoogleAdsService")

        for resource_name in response.resource_names:
            cid = resource_name.split("/")[-1]
            try:
                query = """SELECT customer.id, customer.descriptive_name,
                                  customer.currency_code, customer.time_zone, customer.manager
                           FROM customer LIMIT 1"""
                rows = ga_service.search(customer_id=cid, query=query)
                for row in rows:
                    accessible.append({
                        "customer_id": str(row.customer.id),
                        "name": row.customer.descriptive_name or f"Account {cid}",
                        "is_manager": row.customer.manager,
                        "currency": row.customer.currency_code,
                        "timezone": row.customer.time_zone,
                    })
            except Exception as e:
                # Account might not be accessible for querying (e.g. cancelled)
                logger.warning("Could not query customer", customer_id=cid, error=str(e))
                accessible.append({
                    "customer_id": cid,
                    "name": f"Account {cid}",
                    "is_manager": False,
                    "currency": "",
                    "timezone": "",
                    "error": "Could not fetch details",
                })

        return accessible

    except Exception as e:
        logger.error("Failed to list accessible customers", error=str(e))
        raise HTTPException(status_code=502, detail=f"Google Ads API error: {str(e)}")


@router.post("/{account_id}/select-customer")
async def select_customer(
    account_id: str,
    req: SelectCustomerRequest,
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign a real Google Ads customer_id to a pending integration.
    Also cleans up any other pending duplicates for this tenant.
    """
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.id == account_id,
                IntegrationGoogleAds.tenant_id == user.tenant_id,
            )
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Format customer_id: strip dashes for storage
    clean_id = req.customer_id.replace("-", "").strip()
    if not clean_id.isdigit() or len(clean_id) < 7:
        raise HTTPException(status_code=400, detail="Invalid Google Ads Customer ID")

    account.customer_id = clean_id
    account.account_name = req.account_name or f"Account {clean_id}"
    if req.login_customer_id:
        account.login_customer_id = req.login_customer_id.replace("-", "").strip()

    # Clean up other pending duplicates AND existing duplicates with the same customer_id
    await db.execute(
        delete(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.tenant_id == user.tenant_id,
                IntegrationGoogleAds.id != account_id,
                IntegrationGoogleAds.customer_id.in_(["pending", clean_id]),
            )
        )
    )

    await db.flush()
    logger.info("Customer ID assigned", account_id=account_id, customer_id=clean_id)

    # Trigger initial sync
    from app.jobs.tasks import sync_ads_account_task
    sync_ads_account_task.delay(user.tenant_id, account.id)

    return {
        "id": account.id,
        "customer_id": clean_id,
        "account_name": account.account_name,
        "status": "connected",
        "sync_triggered": True,
    }


@router.delete("/cleanup-pending")
async def cleanup_pending(
    user: CurrentUser = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove all duplicate pending integrations, keeping only the newest one.
    """
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            and_(
                IntegrationGoogleAds.tenant_id == user.tenant_id,
                IntegrationGoogleAds.customer_id == "pending",
            )
        ).order_by(IntegrationGoogleAds.created_at.desc())
    )
    pending = result.scalars().all()

    if len(pending) <= 1:
        return {"removed": 0, "kept": len(pending)}

    # Keep the first (newest), delete the rest
    keep_id = pending[0].id
    to_delete = [p.id for p in pending[1:]]
    await db.execute(
        delete(IntegrationGoogleAds).where(IntegrationGoogleAds.id.in_(to_delete))
    )
    await db.flush()

    return {"removed": len(to_delete), "kept": 1, "kept_id": keep_id}


@router.post("/{account_id}/sync")
async def trigger_sync(
    account_id: str,
    req: Optional[SyncRequest] = None,
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

    if req and req.login_customer_id:
        account.login_customer_id = req.login_customer_id.replace("-", "").strip()
        await db.commit()

    from app.jobs.tasks import sync_ads_account_task
    sync_ads_account_task.delay(user.tenant_id, account.id)

    return {"status": "sync_triggered"}


@router.get("/{account_id}/sync-status")
async def get_sync_status(
    account_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Poll sync progress for a Google Ads account."""
    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.id == account_id,
            IntegrationGoogleAds.tenant_id == user.tenant_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return {
        "sync_status": account.sync_status or "idle",
        "sync_message": account.sync_message,
        "sync_progress": account.sync_progress or 0,
        "sync_started_at": account.sync_started_at.isoformat() if account.sync_started_at else None,
        "sync_error": account.sync_error,
        "campaigns_synced": account.campaigns_synced or 0,
        "conversions_synced": account.conversions_synced or 0,
        "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
    }


@router.post("/diag/trigger-sync")
async def diag_trigger_sync(
    key: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Admin: trigger sync for all active integrations."""
    if key != "gads2026diag":
        raise HTTPException(status_code=403, detail="Invalid key")

    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.is_active == True,
            IntegrationGoogleAds.customer_id != "pending",
        )
    )
    integrations = result.scalars().all()
    triggered = []
    from app.jobs.tasks import sync_ads_account_task
    for ig in integrations:
        sync_ads_account_task.delay(ig.tenant_id, ig.id)
        triggered.append({"tenant_id": ig.tenant_id, "account_id": ig.id, "customer_id": ig.customer_id})

    return {"triggered": len(triggered), "accounts": triggered}


@router.get("/diag/audit-credentials")
async def audit_credentials(
    key: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """TEMPORARY: Audit Google Ads API credentials via REST API (no library)."""
    if key != "gads2026diag":
        raise HTTPException(status_code=403, detail="Invalid key")
    import httpx

    results = {
        "developer_token": settings.GOOGLE_ADS_DEVELOPER_TOKEN[:8] + "...",
        "developer_token_len": len(settings.GOOGLE_ADS_DEVELOPER_TOKEN or ""),
        "client_id": settings.GOOGLE_ADS_CLIENT_ID[:20] + "...",
        "client_secret_len": len(settings.GOOGLE_ADS_CLIENT_SECRET or ""),
    }

    # Find the first active integration
    res = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = res.scalar_one_or_none()
    if not integration:
        results["error"] = "No active integration found"
        return results

    results["customer_id"] = integration.customer_id
    results["login_customer_id"] = integration.login_customer_id

    # Step 1: Decrypt refresh token
    try:
        refresh_token = decrypt_token(integration.refresh_token_encrypted)
        results["refresh_token_prefix"] = refresh_token[:15] + "..."
        results["refresh_token_len"] = len(refresh_token)
    except Exception as e:
        results["decrypt_error"] = str(e)
        return results

    # Step 2: Get fresh access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "refresh_token": refresh_token,
            "client_id": settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
        results["oauth_token_status"] = token_resp.status_code
        if token_resp.status_code != 200:
            results["oauth_token_error"] = token_resp.text[:300]
            return results

        access_token = token_resp.json()["access_token"]
        results["access_token_obtained"] = True

        mgr_cid = "8946883394"
        client_cid = "5795378641"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": settings.GOOGLE_ADS_DEVELOPER_TOKEN,
        }
        headers_login = {**headers, "login-customer-id": mgr_cid}

        # Test across API versions
        for ver in ["v23", "v19", "v17"]:
            lac_resp = await client.get(
                f"https://googleads.googleapis.com/{ver}/customers:listAccessibleCustomers",
                headers=headers_login,
            )
            results[f"lac_{ver}"] = {"status": lac_resp.status_code, "body": lac_resp.text[:300]}

        # Query manager account (v23)
        mgr_resp = await client.post(
            f"https://googleads.googleapis.com/v23/customers/{mgr_cid}/googleAds:search",
            headers=headers_login,
            json={"query": "SELECT customer.id, customer.descriptive_name, customer.manager FROM customer LIMIT 1"},
        )
        results["mgr_query_v23"] = {"status": mgr_resp.status_code, "body": mgr_resp.text[:500]}

        # Query client account WITH login-customer-id (v23)
        client_resp = await client.post(
            f"https://googleads.googleapis.com/v23/customers/{client_cid}/googleAds:search",
            headers=headers_login,
            json={"query": "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1"},
        )
        results["client_with_login_v23"] = {"status": client_resp.status_code, "body": client_resp.text[:500]}

        # Query client account WITHOUT login-customer-id (v23) — test direct access
        client_resp2 = await client.post(
            f"https://googleads.googleapis.com/v23/customers/{client_cid}/googleAds:search",
            headers=headers,
            json={"query": "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1"},
        )
        results["client_no_login_v23"] = {"status": client_resp2.status_code, "body": client_resp2.text[:500]}

    return results
