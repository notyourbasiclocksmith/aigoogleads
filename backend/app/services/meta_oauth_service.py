"""
Meta Ads OAuth Service.
Handles OAuth2 flow for Facebook/Instagram: authorize URL, token exchange, refresh.
Uses raw httpx (same pattern as GBP/Google Ads).
"""
import httpx
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.v2.integration_meta import IntegrationMeta

logger = structlog.get_logger()

META_AUTH_URL = "https://www.facebook.com/v22.0/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/v22.0/oauth/access_token"
META_GRAPH_URL = "https://graph.facebook.com/v22.0"

META_SCOPES = [
    "ads_management",           # Create/edit/delete campaigns, ad sets, ads, creatives
    "ads_read",                 # Read campaign data, insights, performance metrics
    "pages_show_list",          # List Facebook Pages (required to find page_id for creatives)
    "pages_read_engagement",    # Read page engagement metrics
    "pages_manage_ads",         # Use Pages for ad creation (required for object_story_spec)
    "instagram_basic",          # Read Instagram account info (for instagram_user_id)
    "instagram_manage_insights", # Read Instagram insights
    "business_management",      # Access business-level ad accounts and pages
]


def get_authorization_url(tenant_id: str, origin: str = "onboarding") -> str:
    """Generate Meta OAuth authorization URL."""
    params = {
        "client_id": settings.META_APP_ID,
        "redirect_uri": settings.META_REDIRECT_URI,
        "response_type": "code",
        "scope": ",".join(META_SCOPES),
        "state": f"meta:{tenant_id}:{origin}",
    }
    return f"{META_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str, tenant_id: str, db: AsyncSession
) -> Dict:
    """Exchange authorization code for access token, then get long-lived token."""
    # Step 1: Exchange code for short-lived token
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            META_TOKEN_URL,
            params={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "redirect_uri": settings.META_REDIRECT_URI,
                "code": code,
            },
        )

    if resp.status_code != 200:
        logger.error("Meta token exchange failed", status=resp.status_code, response=resp.text[:500])
        raise ValueError(f"Token exchange failed: {resp.text[:200]}")

    data = resp.json()
    short_token = data.get("access_token")
    if not short_token:
        raise ValueError("No access token in response")

    # Step 2: Exchange short-lived token for long-lived token (~60 days)
    async with httpx.AsyncClient() as client:
        ll_resp = await client.get(
            META_TOKEN_URL,
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": short_token,
            },
        )

    if ll_resp.status_code == 200:
        ll_data = ll_resp.json()
        access_token = ll_data.get("access_token", short_token)
        expires_in = ll_data.get("expires_in", 5184000)  # ~60 days default
    else:
        logger.warning("Meta long-lived token exchange failed, using short-lived", status=ll_resp.status_code)
        access_token = short_token
        expires_in = data.get("expires_in", 3600)

    # Store in DB
    result = await db.execute(
        select(IntegrationMeta).where(IntegrationMeta.tenant_id == tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        conn = IntegrationMeta(tenant_id=tenant_id)
        db.add(conn)

    conn.access_token_encrypted = encrypt_token(access_token)
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn.is_active = True
    conn.sync_error = None

    await db.flush()
    logger.info("Meta tokens stored", tenant_id=tenant_id, expires_in=expires_in)
    return {"success": True, "tenant_id": tenant_id}


async def get_valid_access_token(tenant_id: str, db: AsyncSession) -> Optional[str]:
    """Get a valid Meta access token, refreshing if within 7 days of expiry."""
    result = await db.execute(
        select(IntegrationMeta).where(IntegrationMeta.tenant_id == tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn or not conn.access_token_encrypted or not conn.is_active:
        return None

    token = decrypt_token(conn.access_token_encrypted)

    # Refresh if within 7 days of expiry
    if conn.token_expires_at:
        days_left = (conn.token_expires_at - datetime.now(timezone.utc)).days
        if days_left < 7:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        META_TOKEN_URL,
                        params={
                            "grant_type": "fb_exchange_token",
                            "client_id": settings.META_APP_ID,
                            "client_secret": settings.META_APP_SECRET,
                            "fb_exchange_token": token,
                        },
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    new_token = data.get("access_token", token)
                    conn.access_token_encrypted = encrypt_token(new_token)
                    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 5184000))
                    conn.sync_error = None
                    await db.flush()
                    token = new_token
                    logger.info("Meta token refreshed", tenant_id=tenant_id)
            except Exception as e:
                logger.error("Meta token refresh failed", tenant_id=tenant_id, error=str(e))

    return token


async def discover_ad_accounts(access_token: str) -> List[Dict]:
    """List ad accounts accessible by this user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{META_GRAPH_URL}/me/adaccounts",
            params={
                "access_token": access_token,
                "fields": "account_id,name,account_status,currency,business_name",
                "limit": 50,
            },
        )
    if resp.status_code != 200:
        logger.warning("Meta list ad accounts failed", status=resp.status_code, body=resp.text[:300])
        return []
    return resp.json().get("data", [])


async def discover_pixels(access_token: str, ad_account_id: str) -> List[Dict]:
    """List Meta Pixels for an ad account."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{META_GRAPH_URL}/{ad_account_id}/adspixels",
            params={
                "access_token": access_token,
                "fields": "id,name,is_created_by_business",
                "limit": 50,
            },
        )
    if resp.status_code != 200:
        logger.warning("Meta list pixels failed", status=resp.status_code, body=resp.text[:300])
        return []
    return resp.json().get("data", [])


async def discover_pages(access_token: str) -> List[Dict]:
    """List Facebook Pages accessible by this user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{META_GRAPH_URL}/me/accounts",
            params={
                "access_token": access_token,
                "fields": "id,name,category",
                "limit": 50,
            },
        )
    if resp.status_code != 200:
        logger.warning("Meta list pages failed", status=resp.status_code, body=resp.text[:300])
        return []
    return resp.json().get("data", [])
