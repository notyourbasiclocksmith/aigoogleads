"""Module 10 — Alerting & Delivery API Routes"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.v2.notification_channel import NotificationChannel
from app.models.v2.notification_rule import NotificationRule
from app.models.v2.notification_sent import NotificationSent
from app.services.v2.notification_service import dispatch_notification, send_test_notification

router = APIRouter()


class CreateChannelRequest(BaseModel):
    tenant_id: str
    type: str  # slack, email, webhook
    name: Optional[str] = None
    config: dict = {}


class UpdateChannelRequest(BaseModel):
    tenant_id: str
    channel_id: str
    name: Optional[str] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


class CreateRuleRequest(BaseModel):
    tenant_id: str
    event_type: str
    channel_id: Optional[str] = None
    min_severity: str = "warning"
    quiet_start_hour: Optional[int] = None
    quiet_end_hour: Optional[int] = None


class TestNotificationRequest(BaseModel):
    tenant_id: str
    channel_id: str


# ── Channels ──
@router.get("/channels")
async def list_channels(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationChannel).where(NotificationChannel.tenant_id == tenant_id)
    result = await db.execute(stmt)
    channels = result.scalars().all()
    return [
        {
            "id": c.id, "type": c.type, "name": c.name, "config": c.config_json,
            "enabled": c.enabled, "created_at": c.created_at.isoformat(),
        }
        for c in channels
    ]


@router.post("/channels")
async def create_channel(req: CreateChannelRequest, db: AsyncSession = Depends(get_db)):
    if req.type not in ("slack", "email", "webhook"):
        raise HTTPException(400, "type must be slack, email, or webhook")
    channel = NotificationChannel(
        id=str(uuid.uuid4()),
        tenant_id=req.tenant_id,
        type=req.type,
        name=req.name or req.type.title(),
        config_json=req.config,
        enabled=True,
    )
    db.add(channel)
    return {"id": channel.id, "type": channel.type, "name": channel.name}


@router.put("/channels")
async def update_channel(req: UpdateChannelRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationChannel).where(
        and_(NotificationChannel.id == req.channel_id, NotificationChannel.tenant_id == req.tenant_id)
    )
    result = await db.execute(stmt)
    channel = result.scalars().first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    if req.name is not None:
        channel.name = req.name
    if req.config is not None:
        channel.config_json = req.config
    if req.enabled is not None:
        channel.enabled = req.enabled
    return {"id": channel.id, "updated": True}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str, tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationChannel).where(
        and_(NotificationChannel.id == channel_id, NotificationChannel.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    channel = result.scalars().first()
    if not channel:
        raise HTTPException(404, "Channel not found")
    await db.delete(channel)
    return {"deleted": True}


# ── Rules ──
@router.get("/rules")
async def list_rules(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationRule).where(NotificationRule.tenant_id == tenant_id)
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return [
        {
            "id": r.id, "event_type": r.event_type, "channel_id": r.channel_id,
            "min_severity": r.min_severity, "quiet_start_hour": r.quiet_start_hour,
            "quiet_end_hour": r.quiet_end_hour, "enabled": r.enabled,
        }
        for r in rules
    ]


@router.post("/rules")
async def create_rule(req: CreateRuleRequest, db: AsyncSession = Depends(get_db)):
    rule = NotificationRule(
        id=str(uuid.uuid4()),
        tenant_id=req.tenant_id,
        event_type=req.event_type,
        channel_id=req.channel_id,
        min_severity=req.min_severity,
        quiet_start_hour=req.quiet_start_hour,
        quiet_end_hour=req.quiet_end_hour,
        enabled=True,
    )
    db.add(rule)
    return {"id": rule.id, "event_type": rule.event_type}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationRule).where(
        and_(NotificationRule.id == rule_id, NotificationRule.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    return {"deleted": True}


# ── Test & History ──
@router.post("/test")
async def test_notification(req: TestNotificationRequest, db: AsyncSession = Depends(get_db)):
    return await send_test_notification(db, req.tenant_id, req.channel_id)


@router.get("/history")
async def notification_history(tenant_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(NotificationSent)
        .where(NotificationSent.tenant_id == tenant_id)
        .order_by(NotificationSent.sent_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    sent = result.scalars().all()
    return [
        {
            "id": s.id, "event_type": s.event_type, "channel_id": s.channel_id,
            "status": s.status, "payload": s.payload_json,
            "sent_at": s.sent_at.isoformat(),
        }
        for s in sent
    ]
