"""
Google Business Profile OAuth Service.
Handles OAuth2 flow for GBP: authorize URL, token exchange, refresh.
Uses the Google My Business API (now Business Profile API).
"""
import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token
from app.models.gbp_connection import GBPConnection

logger = structlog.get_logger()

# GBP OAuth scope
GBP_SCOPES = [
    "https://www.googleapis.com/auth/business.manage",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.GBP_CLIENT_ID or settings.GOOGLE_ADS_CLIENT_ID,
            "client_secret": settings.GBP_CLIENT_SECRET or settings.GOOGLE_ADS_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GBP_REDIRECT_URI],
        }
    }


def get_authorization_url(tenant_id: str, origin: str = "onboarding") -> str:
    """Generate GBP OAuth authorization URL."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=GBP_SCOPES,
        redirect_uri=settings.GBP_REDIRECT_URI,
    )
    authorization_url, _state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=f"gbp:{tenant_id}:{origin}",
    )
    return authorization_url


async def exchange_code_for_tokens(
    code: str, tenant_id: str, db: AsyncSession
) -> Dict:
    """Exchange authorization code for access & refresh tokens, store in DB."""
    import warnings

    flow = Flow.from_client_config(
        _client_config(),
        scopes=GBP_SCOPES,
        redirect_uri=settings.GBP_REDIRECT_URI,
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Scope has changed")
        flow.fetch_token(code=code)

    creds = flow.credentials

    result = await db.execute(
        select(GBPConnection).where(GBPConnection.tenant_id == tenant_id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        conn = GBPConnection(tenant_id=tenant_id)
        db.add(conn)

    conn.access_token_encrypted = encrypt_token(creds.token)
    if creds.refresh_token:
        conn.refresh_token_encrypted = encrypt_token(creds.refresh_token)
    conn.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=3600)
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

    cfg = _client_config()["web"]
    creds = Credentials(
        token=token,
        refresh_token=refresh_token,
        token_uri=cfg["token_uri"],
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
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
