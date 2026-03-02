"""
Module 10 — Alerting & Delivery (Slack / Email / Webhooks)
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.v2.notification_channel import NotificationChannel
from app.models.v2.notification_rule import NotificationRule
from app.models.v2.notification_sent import NotificationSent
from app.models.v2.connector import Connector
from app.services.v2.connector_framework import get_connector_instance

logger = structlog.get_logger()


async def get_channels(db: AsyncSession, tenant_id: str) -> List[NotificationChannel]:
    stmt = select(NotificationChannel).where(
        and_(NotificationChannel.tenant_id == tenant_id, NotificationChannel.enabled == True)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_rules_for_event(db: AsyncSession, tenant_id: str, event_type: str) -> List[NotificationRule]:
    stmt = select(NotificationRule).where(
        and_(
            NotificationRule.tenant_id == tenant_id,
            NotificationRule.event_type == event_type,
            NotificationRule.enabled == True,
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _is_in_quiet_hours(rule: NotificationRule, current_hour: int) -> bool:
    if rule.quiet_start_hour is None or rule.quiet_end_hour is None:
        return False
    if rule.quiet_start_hour <= rule.quiet_end_hour:
        return rule.quiet_start_hour <= current_hour < rule.quiet_end_hour
    else:
        return current_hour >= rule.quiet_start_hour or current_hour < rule.quiet_end_hour


async def dispatch_notification(
    db: AsyncSession,
    tenant_id: str,
    event_type: str,
    severity: str,
    payload: Dict[str, Any],
    alert_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Dispatch a notification to all matching channels for a tenant.
    Returns list of delivery results.
    """
    rules = await get_rules_for_event(db, tenant_id, event_type)
    if not rules:
        rules = await get_rules_for_event(db, tenant_id, "*")

    severity_rank = {"info": 0, "warning": 1, "error": 2, "critical": 3}
    current_hour = datetime.now(timezone.utc).hour
    results = []

    for rule in rules:
        min_sev = severity_rank.get(rule.min_severity, 1)
        event_sev = severity_rank.get(severity, 1)
        if event_sev < min_sev:
            continue
        if _is_in_quiet_hours(rule, current_hour):
            continue

        channel = None
        if rule.channel_id:
            ch_stmt = select(NotificationChannel).where(NotificationChannel.id == rule.channel_id)
            ch_result = await db.execute(ch_stmt)
            channel = ch_result.scalars().first()

        if not channel:
            continue

        delivery_result = await _deliver_to_channel(db, tenant_id, channel, event_type, payload, alert_id)
        results.append(delivery_result)

    return results


async def _deliver_to_channel(
    db: AsyncSession,
    tenant_id: str,
    channel: NotificationChannel,
    event_type: str,
    payload: Dict[str, Any],
    alert_id: Optional[str],
) -> Dict[str, Any]:
    """Deliver notification via a specific channel."""
    status = "sent"
    try:
        if channel.type == "slack":
            await _send_slack(channel, event_type, payload)
        elif channel.type == "email":
            await _send_email(channel, event_type, payload)
        elif channel.type == "webhook":
            await _send_webhook(channel, event_type, payload)
        else:
            status = "failed"
    except Exception as e:
        logger.error("Notification delivery failed", channel_id=channel.id, error=str(e))
        status = "failed"

    sent = NotificationSent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        alert_id=alert_id,
        channel_id=channel.id,
        event_type=event_type,
        payload_json=payload,
        status=status,
    )
    db.add(sent)
    return {"channel_id": channel.id, "channel_type": channel.type, "status": status}


async def _send_slack(channel: NotificationChannel, event_type: str, payload: Dict[str, Any]):
    import httpx
    webhook_url = channel.config_json.get("webhook_url", "")
    if not webhook_url:
        raise ValueError("Slack webhook URL not configured")

    message = payload.get("message", f"[{event_type}] Notification from Ignite Ads AI")
    slack_payload = {
        "text": message,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"🔔 {event_type}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        ],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=slack_payload)
        resp.raise_for_status()


async def _send_email(channel: NotificationChannel, event_type: str, payload: Dict[str, Any]):
    # Stub: integrate with SendGrid/Mailgun
    logger.info("Email notification stub", event_type=event_type, to=channel.config_json.get("to_email"))


async def _send_webhook(channel: NotificationChannel, event_type: str, payload: Dict[str, Any]):
    import httpx
    url = channel.config_json.get("url", "")
    if not url:
        raise ValueError("Webhook URL not configured")

    webhook_payload = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }
    headers = channel.config_json.get("headers", {})
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=webhook_payload, headers=headers)
        resp.raise_for_status()


async def send_test_notification(db: AsyncSession, tenant_id: str, channel_id: str) -> Dict[str, Any]:
    """Send a test notification to verify channel configuration."""
    stmt = select(NotificationChannel).where(
        and_(NotificationChannel.id == channel_id, NotificationChannel.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    channel = result.scalars().first()
    if not channel:
        return {"error": "Channel not found"}

    test_payload = {
        "message": "🧪 Test notification from Ignite Ads AI. If you see this, your channel is configured correctly!",
        "test": True,
    }
    return await _deliver_to_channel(db, tenant_id, channel, "test", test_payload, None)
