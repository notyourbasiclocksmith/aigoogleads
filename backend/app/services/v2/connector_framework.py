"""
Module 4 — Connector Framework
Abstract base + concrete stubs for CRM, Slack, Email, Meta, TikTok, YouTube, Generic Webhook.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid
import json
import httpx
import structlog
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.v2.connector import Connector
from app.models.v2.connector_event import ConnectorEvent

logger = structlog.get_logger()


# ── Encryption helpers ──
def _fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)


def encrypt_credentials(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(token: str) -> dict:
    return json.loads(_fernet().decrypt(token.encode()).decode())


# ── Abstract Base Connector ──
class BaseConnector(ABC):
    """All connectors implement this interface."""

    connector_type: str = "base"

    def __init__(self, connector: Connector, db: AsyncSession):
        self.connector = connector
        self.db = db
        self.config: dict = connector.config_json or {}

    async def _log_event(self, level: str, message: str, payload: dict | None = None):
        event = ConnectorEvent(
            id=str(uuid.uuid4()),
            tenant_id=self.connector.tenant_id,
            connector_id=self.connector.id,
            level=level,
            message=message,
            payload_json=payload or {},
        )
        self.db.add(event)

    @abstractmethod
    async def connect(self, credentials: dict) -> bool:
        """Establish connection / validate credentials. Return True on success."""
        ...

    @abstractmethod
    async def sync(self) -> dict:
        """Pull data from the external system. Return summary dict."""
        ...

    @abstractmethod
    async def push(self, payload: dict) -> dict:
        """Push data to the external system. Return result dict."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Return {"healthy": bool, "message": str}."""
        ...


# ── CRM Connector Stub (IntelliDriveOS) ──
class CRMConnector(BaseConnector):
    connector_type = "crm"

    async def connect(self, credentials: dict) -> bool:
        api_key = credentials.get("api_key", "")
        if not api_key:
            await self._log_event("error", "Missing API key for CRM connector")
            return False
        self.connector.credentials_encrypted = encrypt_credentials({"api_key": api_key})
        self.connector.status = "connected"
        await self._log_event("info", "CRM connector connected successfully")
        return True

    async def sync(self) -> dict:
        if not self.connector.credentials_encrypted:
            return {"error": "Not connected"}
        creds = decrypt_credentials(self.connector.credentials_encrypted)
        # Stub: would call CRM API to pull closed jobs, revenue, services
        await self._log_event("info", "CRM sync executed (stub)")
        self.connector.last_sync_at = datetime.now(timezone.utc)
        return {"synced": True, "records": 0, "stub": True}

    async def push(self, payload: dict) -> dict:
        # Stub: would push offline conversions from CRM data
        await self._log_event("info", "CRM push executed (stub)", payload)
        return {"pushed": True, "stub": True}

    async def health_check(self) -> dict:
        if self.connector.status == "connected":
            return {"healthy": True, "message": "CRM connector is connected"}
        return {"healthy": False, "message": "CRM connector is not connected"}


# ── Slack Webhook Connector ──
class SlackWebhookConnector(BaseConnector):
    connector_type = "slack_webhook"

    async def connect(self, credentials: dict) -> bool:
        webhook_url = credentials.get("webhook_url", "")
        if not webhook_url or not webhook_url.startswith("https://hooks.slack.com/"):
            await self._log_event("error", "Invalid Slack webhook URL")
            return False
        self.connector.credentials_encrypted = encrypt_credentials({"webhook_url": webhook_url})
        self.connector.status = "connected"
        await self._log_event("info", "Slack webhook connector connected")
        return True

    async def sync(self) -> dict:
        return {"synced": False, "message": "Slack webhooks are push-only"}

    async def push(self, payload: dict) -> dict:
        if not self.connector.credentials_encrypted:
            return {"error": "Not connected"}
        creds = decrypt_credentials(self.connector.credentials_encrypted)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(creds["webhook_url"], json=payload)
                resp.raise_for_status()
            await self._log_event("info", "Slack message sent", {"status": resp.status_code})
            return {"sent": True}
        except Exception as e:
            await self._log_event("error", f"Slack send failed: {e}")
            return {"sent": False, "error": str(e)}

    async def health_check(self) -> dict:
        return {"healthy": self.connector.status == "connected", "message": "Slack webhook"}


# ── Email Connector (SendGrid/Mailgun stub) ──
class EmailConnector(BaseConnector):
    connector_type = "email"

    async def connect(self, credentials: dict) -> bool:
        api_key = credentials.get("api_key", "")
        from_email = credentials.get("from_email", "")
        if not api_key or not from_email:
            await self._log_event("error", "Missing api_key or from_email")
            return False
        self.connector.credentials_encrypted = encrypt_credentials(credentials)
        self.connector.status = "connected"
        await self._log_event("info", "Email connector connected")
        return True

    async def sync(self) -> dict:
        return {"synced": False, "message": "Email is push-only"}

    async def push(self, payload: dict) -> dict:
        if not self.connector.credentials_encrypted:
            return {"error": "Not connected"}

        import httpx
        creds = decrypt_credentials(self.connector.credentials_encrypted)
        api_key = creds.get("api_key", "")
        from_email = creds.get("from_email", "")

        to_email = payload.get("to_email", "")
        subject = payload.get("subject", "Notification from IntelliAds AI")
        body = payload.get("body", payload.get("message", ""))

        if not to_email:
            return {"error": "to_email required in payload"}

        sendgrid_payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email, "name": "IntelliAds AI"},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body},
                {"type": "text/html", "value": f"<p>{body}</p>"},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=sendgrid_payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code not in (200, 201, 202):
                    await self._log_event("error", f"SendGrid error {resp.status_code}: {resp.text[:200]}")
                    return {"sent": False, "error": f"SendGrid {resp.status_code}"}
        except Exception as e:
            await self._log_event("error", f"SendGrid exception: {str(e)}")
            return {"sent": False, "error": str(e)}

        await self._log_event("info", f"Email sent to {to_email}", payload)
        return {"sent": True}

    async def health_check(self) -> dict:
        if self.connector.status != "connected" or not self.connector.credentials_encrypted:
            return {"healthy": False, "message": "Email connector not connected"}

        import httpx
        creds = decrypt_credentials(self.connector.credentials_encrypted)
        api_key = creds.get("api_key", "")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.sendgrid.com/v3/scopes",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                healthy = resp.status_code == 200
                return {"healthy": healthy, "message": "SendGrid API reachable" if healthy else f"SendGrid {resp.status_code}"}
        except Exception as e:
            return {"healthy": False, "message": str(e)}


# ── Generic Webhook Connector ──
class GenericWebhookConnector(BaseConnector):
    connector_type = "generic_webhook"

    async def connect(self, credentials: dict) -> bool:
        url = credentials.get("url", "")
        if not url:
            await self._log_event("error", "Missing webhook URL")
            return False
        self.connector.credentials_encrypted = encrypt_credentials(credentials)
        self.connector.status = "connected"
        await self._log_event("info", "Generic webhook connector connected")
        return True

    async def sync(self) -> dict:
        return {"synced": False, "message": "Webhooks are push-only"}

    async def push(self, payload: dict) -> dict:
        if not self.connector.credentials_encrypted:
            return {"error": "Not connected"}
        creds = decrypt_credentials(self.connector.credentials_encrypted)
        headers = creds.get("headers", {})
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(creds["url"], json=payload, headers=headers)
                resp.raise_for_status()
            await self._log_event("info", "Webhook sent", {"status": resp.status_code})
            return {"sent": True, "status_code": resp.status_code}
        except Exception as e:
            await self._log_event("error", f"Webhook failed: {e}")
            return {"sent": False, "error": str(e)}

    async def health_check(self) -> dict:
        return {"healthy": self.connector.status == "connected", "message": "Generic webhook"}


# ── Future Ads Connector Stubs ──
class MetaAdsConnectorStub(BaseConnector):
    connector_type = "meta_ads"

    async def connect(self, credentials: dict) -> bool:
        await self._log_event("info", "Meta Ads connector stub — not yet implemented")
        self.connector.status = "disconnected"
        return False

    async def sync(self) -> dict:
        return {"stub": True, "message": "Meta Ads sync not implemented"}

    async def push(self, payload: dict) -> dict:
        return {"stub": True, "message": "Meta Ads push not implemented"}

    async def health_check(self) -> dict:
        return {"healthy": False, "message": "Meta Ads connector not yet implemented"}


class TikTokAdsConnectorStub(BaseConnector):
    connector_type = "tiktok_ads"

    async def connect(self, credentials: dict) -> bool:
        await self._log_event("info", "TikTok Ads connector stub — not yet implemented")
        self.connector.status = "disconnected"
        return False

    async def sync(self) -> dict:
        return {"stub": True, "message": "TikTok Ads sync not implemented"}

    async def push(self, payload: dict) -> dict:
        return {"stub": True, "message": "TikTok Ads push not implemented"}

    async def health_check(self) -> dict:
        return {"healthy": False, "message": "TikTok Ads connector not yet implemented"}


class YouTubeAdsConnectorStub(BaseConnector):
    connector_type = "youtube_ads"

    async def connect(self, credentials: dict) -> bool:
        await self._log_event("info", "YouTube Ads connector stub — not yet implemented")
        self.connector.status = "disconnected"
        return False

    async def sync(self) -> dict:
        return {"stub": True, "message": "YouTube Ads sync not implemented"}

    async def push(self, payload: dict) -> dict:
        return {"stub": True, "message": "YouTube Ads push not implemented"}

    async def health_check(self) -> dict:
        return {"healthy": False, "message": "YouTube Ads connector not yet implemented"}


# ── Registry ──
CONNECTOR_REGISTRY: Dict[str, type] = {
    "crm": CRMConnector,
    "slack_webhook": SlackWebhookConnector,
    "email": EmailConnector,
    "generic_webhook": GenericWebhookConnector,
    "meta_ads": MetaAdsConnectorStub,
    "tiktok_ads": TikTokAdsConnectorStub,
    "youtube_ads": YouTubeAdsConnectorStub,
}


def get_connector_instance(connector: Connector, db: AsyncSession) -> BaseConnector:
    cls = CONNECTOR_REGISTRY.get(connector.type)
    if not cls:
        raise ValueError(f"Unknown connector type: {connector.type}")
    return cls(connector=connector, db=db)
