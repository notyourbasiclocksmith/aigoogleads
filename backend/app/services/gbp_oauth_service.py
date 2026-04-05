"""
Google Business Profile OAuth Service.
Handles OAuth2 flow for GBP: authorize URL, token exchange, refresh.
Uses raw httpx like Google Ads OAuth to avoid PKCE/session issues.
"""
import httpx
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from urllib.parse import urlencode

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.gbp_connection import GBPConnection

logger = structlog.get_logger()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GBP_SCOPES = [
    "https://www.googleapis.com/auth/business.manage",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

def _client_id() -> str:
    return settings.GBP_CLIENT_ID or settings.GOOGLE_ADS_CLIENT_ID

def _client_secret() -> str:
    return settings.GBP_CLIENT_SECRET or settings.GOOGLE_ADS_CLIENT_SECRET


def get_authorization_url(tenant_id: str, origin: str = "onboarding") -> str:
    """Generate GBP OAuth authorization URL."""
    params = {
        "client_id": _client_id(),
        "redirect_uri": settings.GBP_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GBP_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": f"gbp:{tenant_id}:{origin}",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(
    code: str, tenant_id: str, db: AsyncSession
) -> Dict:
    """Exchange authorization code for access & refresh tokens, store in DB."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": settings.GBP_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        logger.error(
            "GBP token exchange failed",
            status=resp.status_code,
            response=resp.text[:500],
            client_id_prefix=_client_id()[:20],
        )
        raise ValueError(f"Token exchange failed: {resp.text[:200]}")

    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if not access_token:
        raise ValueError("No access token in response")

    result = await db.execute(
        select(GBPConnection).where(GBPConnection.tenant_id == tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        conn = GBPConnection(tenant_id=tenant_id)
        db.add(conn)

    conn.access_token_encrypted = encrypt_token(access_token)
    if refresh_token:
        conn.refresh_token_encrypted = encrypt_token(refresh_token)
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=data.get("expires_in", 3600)
    )
    conn.is_active = True
    conn.sync_error = None

    await db.flush()
    logger.info("GBP tokens stored", tenant_id=tenant_id)
    return {"success": True, "tenant_id": tenant_id}


async def get_credentials(tenant_id: str, db: AsyncSession) -> Optional[Credentials]:
    """Get valid GBP credentials, refreshing if needed."""
    result = await db.execute(
        select(GBPConnection).where(GBPConnection.tenant_id == tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn or not conn.access_token_encrypted:
        return None

    token = decrypt_token(conn.access_token_encrypted)
    refresh_token = (
        decrypt_token(conn.refresh_token_encrypted)
        if conn.refresh_token_encrypted
        else None
    )

    creds = Credentials(
        token=token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=_client_id(),
        client_secret=_client_secret(),
    )

    # Refresh if expired
    if conn.token_expires_at and datetime.now(timezone.utc) >= conn.token_expires_at:
        try:
            creds.refresh(Request())
            conn.access_token_encrypted = encrypt_token(creds.token)
            conn.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=3600)
            conn.sync_error = None
            await db.flush()
        except Exception as e:
            logger.error("GBP token refresh failed", tenant_id=tenant_id, error=str(e))
            conn.sync_error = str(e)
            await db.flush()
            return None

    return creds
