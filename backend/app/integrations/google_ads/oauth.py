"""
Google Ads OAuth — Connect + token refresh
"""
import httpx
import structlog
from typing import Dict, Any, Optional
from app.core.config import settings

logger = structlog.get_logger()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "https://www.googleapis.com/auth/adwords"


def get_oauth_url(state: str = "") -> str:
    params = {
        "client_id": settings.GOOGLE_ADS_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_ADS_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{qs}"


async def exchange_code_for_tokens(auth_code: str) -> Optional[Dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": auth_code,
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_ADS_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            logger.error("OAuth token exchange failed",
                         status=resp.status_code,
                         response=resp.text[:500],
                         client_id_prefix=settings.GOOGLE_ADS_CLIENT_ID[:15],
                         redirect_uri=settings.GOOGLE_ADS_REDIRECT_URI)
            return None
        data = resp.json()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type"),
        }


class OAuthTokenExpiredError(Exception):
    """Raised when the refresh token has been expired or revoked by Google."""
    pass


async def refresh_access_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "client_secret": settings.GOOGLE_ADS_CLIENT_SECRET,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            body = resp.text[:500]
            logger.error("OAuth token refresh failed",
                         status=resp.status_code,
                         response=body,
                         client_id_prefix=settings.GOOGLE_ADS_CLIENT_ID[:15])
            if "invalid_grant" in body:
                raise OAuthTokenExpiredError(
                    "Your Google Ads connection has expired or been revoked. "
                    "Please reconnect your account in Settings → Google Ads → Reconnect."
                )
            return None
        data = resp.json()
        return {
            "access_token": data.get("access_token"),
            "expires_in": data.get("expires_in"),
        }
