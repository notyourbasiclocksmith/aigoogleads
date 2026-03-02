"""
Google Ads OAuth — Connect + token refresh
"""
import httpx
from typing import Dict, Any, Optional
from app.core.config import settings

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
            return None
        data = resp.json()
        return {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
            "token_type": data.get("token_type"),
        }


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
            return None
        data = resp.json()
        return {
            "access_token": data.get("access_token"),
            "expires_in": data.get("expires_in"),
        }
