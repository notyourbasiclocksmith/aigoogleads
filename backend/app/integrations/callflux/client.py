"""
CallFlux Integration Client — Manages call tracking for Google Ads campaigns.

Every new campaign gets a CallFlux tracking number automatically:
  1. Ensure tenant exists in CallFlux (auto-register on first use)
  2. Create a CallFlux campaign (mirrors the Google Ads campaign)
  3. Purchase a tracking phone number from Twilio via CallFlux
  4. Configure forwarding to the business's real phone number
  5. Return tracking number for use in:
     - Google Ads call extensions
     - Landing page CTAs
     - Ad headlines/descriptions

The tracking number enables:
  - Call attribution (which ad/keyword drove the call)
  - GCLID matching (offline conversions back to Google Ads)
  - Call recording + AI transcription
  - Lead scoring + sentiment analysis
  - Real-time call analytics in dashboard
"""
import json
from typing import Dict, Any, Optional, List

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Timeout for CallFlux API calls (Twilio number purchase can be slow)
CALLFLUX_TIMEOUT = 30.0


class CallFluxClient:
    """Client for CallFlux call tracking API.

    Authentication: Uses the external/service-to-service API for read operations
    and JWT auth for write operations (register, purchase numbers).

    Tenant mapping: Each AI Google Ads tenant maps to a CallFlux tenant.
    The mapping is stored in the Tenant model (callflux_tenant_id, callflux_tokens).
    """

    def __init__(self):
        self.base_url = (settings.CALLFLUX_API_URL or "").rstrip("/")
        self.bridge_api_key = settings.CALLFLUX_BRIDGE_API_KEY or ""

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _s2s_headers(self, callflux_tenant_id: str = "") -> Dict[str, str]:
        """Headers for service-to-service (read) calls."""
        headers = {
            "Content-Type": "application/json",
            "X-Internal-API-Key": self.bridge_api_key,
        }
        if callflux_tenant_id:
            headers["X-Tenant-ID"] = str(callflux_tenant_id)
        return headers

    def _auth_headers(self, access_token: str) -> Dict[str, str]:
        """Headers for authenticated (write) calls."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

    # ── TENANT REGISTRATION ──────────────────────────────────────

    async def register_tenant(
        self,
        tenant_name: str,
        email: str,
        password: str = "",
    ) -> Dict[str, Any]:
        """
        Register a new CallFlux tenant (auto-called on first campaign creation).

        Returns:
        {
            "tenant_id": 123,
            "user_id": 456,
            "access_token": "jwt...",
            "refresh_token": "jwt...",
        }
        """
        if not self.is_configured:
            return {"error": "CallFlux not configured"}

        # Generate a secure password if not provided
        if not password:
            import secrets
            password = secrets.token_urlsafe(24)

        payload = {
            "tenant_name": tenant_name,
            "email": email,
            "password": password,
        }

        url = f"{self.base_url}/api/auth/register"
        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info("CallFlux tenant registered",
                        tenant_name=tenant_name, email=email)
                    return {
                        "access_token": data.get("access_token", ""),
                        "refresh_token": data.get("refresh_token", ""),
                        "tenant_id": data.get("tenant_id"),
                        "user_id": data.get("user_id"),
                        "password": password,
                    }
                elif resp.status_code == 409:
                    # Tenant/email already exists — try login instead
                    logger.info("CallFlux tenant already exists, attempting login",
                        email=email)
                    return await self.login(email, password)
                elif resp.status_code == 404:
                    logger.error("CallFlux registration endpoint not found (404). "
                        "Check CALLFLUX_API_URL configuration — the API may be "
                        "down or the URL may be incorrect.",
                        url=url, base_url=self.base_url)
                    return {"error": f"CallFlux API not reachable (404). Verify CALLFLUX_API_URL={self.base_url} is correct and the service is running."}
                else:
                    logger.error("CallFlux registration failed",
                        status=resp.status_code, url=url, body=resp.text[:200])
                    return {"error": f"Registration failed: {resp.status_code}"}
        except httpx.ConnectError as e:
            logger.error("CallFlux connection failed — service may be down or URL is wrong",
                url=url, error=str(e))
            return {"error": f"Cannot connect to CallFlux at {self.base_url}. Check CALLFLUX_API_URL."}
        except Exception as e:
            logger.error("CallFlux registration error", url=url, error=str(e))
            return {"error": str(e)}

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """Login to CallFlux and get tokens."""
        if not self.is_configured:
            return {"error": "CallFlux not configured"}

        url = f"{self.base_url}/api/auth/login"
        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.post(url, json={"email": email, "password": password})
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "access_token": data.get("access_token", ""),
                        "refresh_token": data.get("refresh_token", ""),
                    }
                elif resp.status_code == 404:
                    logger.error("CallFlux login endpoint not found (404)",
                        url=url, base_url=self.base_url)
                    return {"error": f"CallFlux API not reachable (404). Verify CALLFLUX_API_URL={self.base_url}"}
                return {"error": f"Login failed: {resp.status_code}"}
        except httpx.ConnectError as e:
            logger.error("CallFlux login connection failed", url=url, error=str(e))
            return {"error": f"Cannot connect to CallFlux at {self.base_url}"}
        except Exception as e:
            return {"error": str(e)}

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh the CallFlux access token."""
        if not self.is_configured:
            return {"error": "CallFlux not configured"}

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/auth/refresh",
                    json={"refresh_token": refresh_token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"access_token": data.get("access_token", "")}
                return {"error": f"Token refresh failed: {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    # ── CAMPAIGN MANAGEMENT ──────────────────────────────────────

    async def create_campaign(
        self,
        access_token: str,
        campaign_name: str,
        channel: str = "google_ads",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Create a CallFlux campaign (mirrors a Google Ads campaign).

        Returns:
        {
            "campaign_id": 789,
            "name": "A.X | BMW Key Programming | DFW",
            "channel": "google_ads",
        }
        """
        if not self.is_configured:
            return {"error": "CallFlux not configured"}

        payload = {
            "name": campaign_name,
            "channel": channel,
            "notes": notes or f"Auto-created by AI Google Ads platform",
        }

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/campaigns",
                    json=payload,
                    headers=self._auth_headers(access_token),
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info("CallFlux campaign created",
                        campaign_name=campaign_name,
                        campaign_id=data.get("id") or data.get("campaign_id"))
                    return {
                        "campaign_id": data.get("id") or data.get("campaign_id"),
                        "name": data.get("name", campaign_name),
                        "channel": channel,
                    }
                else:
                    logger.error("CallFlux campaign creation failed",
                        status=resp.status_code, body=resp.text[:200])
                    return {"error": f"Campaign creation failed: {resp.status_code}"}
        except Exception as e:
            logger.error("CallFlux campaign creation error", error=str(e))
            return {"error": str(e)}

    # ── PHONE NUMBER PROVISIONING ────────────────────────────────

    async def search_numbers(
        self,
        access_token: str,
        area_code: str = "",
        contains: str = "",
    ) -> List[Dict[str, Any]]:
        """Search available phone numbers from Twilio via CallFlux."""
        if not self.is_configured:
            return []

        params = {}
        if area_code:
            params["area_code"] = area_code
        if contains:
            params["contains"] = contains

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/api/phone-numbers/search",
                    params=params,
                    headers=self._auth_headers(access_token),
                )
                if resp.status_code == 200:
                    return resp.json() if isinstance(resp.json(), list) else resp.json().get("numbers", [])
                return []
        except Exception as e:
            logger.error("CallFlux number search error", error=str(e))
            return []

    async def purchase_tracking_number(
        self,
        access_token: str,
        campaign_id: int,
        forward_to_number: str,
        area_code: str = "",
        record_calls: bool = True,
        whisper_message: str = "",
    ) -> Dict[str, Any]:
        """
        Purchase a tracking phone number and assign it to a campaign.

        This is the core integration — every Google Ads campaign gets a
        dedicated tracking number that:
        - Forwards to the business's real phone
        - Records calls for transcription + AI analysis
        - Tracks which ad/keyword drove the call (via GCLID/DNI)
        - Reports conversions back to Google Ads

        Returns:
        {
            "phone_number_id": 101,
            "phone_number": "+12145551234",
            "forward_to": "+12145559876",
            "campaign_id": 789,
            "status": "ACTIVE",
        }
        """
        if not self.is_configured:
            return {"error": "CallFlux not configured"}

        payload = {
            "area_code": area_code or "214",  # Default to DFW area code
            "campaign_id": campaign_id,
            "forward_to_number": forward_to_number,
            "record_calls": record_calls,
            "tracking_source": "google_ads",
        }
        if whisper_message:
            payload["whisper_message"] = whisper_message

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/phone-numbers/purchase",
                    json=payload,
                    headers=self._auth_headers(access_token),
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    phone = data.get("phone_number", "")
                    logger.info("CallFlux tracking number purchased",
                        phone=phone,
                        campaign_id=campaign_id,
                        forward_to=forward_to_number)
                    return {
                        "phone_number_id": data.get("id") or data.get("phone_number_id"),
                        "phone_number": phone,
                        "forward_to": forward_to_number,
                        "campaign_id": campaign_id,
                        "status": data.get("status", "ACTIVE"),
                        "twilio_sid": data.get("twilio_sid", ""),
                    }
                else:
                    logger.error("CallFlux number purchase failed",
                        status=resp.status_code, body=resp.text[:300])
                    return {"error": f"Number purchase failed: {resp.status_code} - {resp.text[:100]}"}
        except Exception as e:
            logger.error("CallFlux number purchase error", error=str(e))
            return {"error": str(e)}

    # ── DNI (DYNAMIC NUMBER INSERTION) ───────────────────────────

    async def create_dni_pool(
        self,
        access_token: str,
        pool_name: str,
        purpose: str = "GOOGLE_ADS",
    ) -> Dict[str, Any]:
        """Create a DNI number pool for website call tracking with GCLID attribution."""
        if not self.is_configured:
            return {"error": "CallFlux not configured"}

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/dni/pools",
                    json={"name": pool_name, "purpose": purpose},
                    headers=self._auth_headers(access_token),
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "pool_id": data.get("id") or data.get("pool_id"),
                        "name": pool_name,
                        "purpose": purpose,
                    }
                return {"error": f"DNI pool creation failed: {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    # ── CALL DATA (Read via S2S API) ─────────────────────────────

    async def get_calls(
        self,
        callflux_tenant_id: str,
        campaign_id: Optional[int] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Get calls from CallFlux for a tenant (via S2S API)."""
        if not self.is_configured or not self.bridge_api_key:
            return []

        params = {"days": days}
        if campaign_id:
            params["campaign_id"] = campaign_id

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/api/external/calls",
                    params=params,
                    headers=self._s2s_headers(callflux_tenant_id),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("calls", data) if isinstance(data, dict) else data
                return []
        except Exception as e:
            logger.error("CallFlux get_calls error", error=str(e))
            return []

    async def get_attribution(
        self,
        callflux_tenant_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get Google Ads attribution data from CallFlux."""
        if not self.is_configured or not self.bridge_api_key:
            return {}

        try:
            async with httpx.AsyncClient(timeout=CALLFLUX_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/api/external/attribution",
                    params={"days": days},
                    headers=self._s2s_headers(callflux_tenant_id),
                )
                if resp.status_code == 200:
                    return resp.json()
                return {}
        except Exception as e:
            return {}

    # ── HIGH-LEVEL: Full Campaign Setup ──────────────────────────

    async def setup_campaign_tracking(
        self,
        access_token: str,
        campaign_name: str,
        forward_to_number: str,
        area_code: str = "",
        record_calls: bool = True,
        whisper_message: str = "",
    ) -> Dict[str, Any]:
        """
        High-level helper: Create campaign + purchase tracking number in one call.

        This is what the campaign pipeline calls.

        Returns:
        {
            "campaign_id": 789,
            "phone_number_id": 101,
            "tracking_number": "+12145551234",
            "forward_to": "+12145559876",
            "status": "active",
        }
        """
        # Step 1: Create CallFlux campaign
        campaign = await self.create_campaign(
            access_token=access_token,
            campaign_name=campaign_name,
            channel="google_ads",
        )
        if campaign.get("error"):
            return campaign

        campaign_id = campaign["campaign_id"]

        # Step 2: Purchase tracking number
        number = await self.purchase_tracking_number(
            access_token=access_token,
            campaign_id=campaign_id,
            forward_to_number=forward_to_number,
            area_code=area_code,
            record_calls=record_calls,
            whisper_message=whisper_message,
        )
        if number.get("error"):
            return {**campaign, "tracking_error": number["error"]}

        return {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "phone_number_id": number.get("phone_number_id"),
            "tracking_number": number.get("phone_number", ""),
            "forward_to": forward_to_number,
            "status": "active",
        }


# Singleton
callflux_client = CallFluxClient()
