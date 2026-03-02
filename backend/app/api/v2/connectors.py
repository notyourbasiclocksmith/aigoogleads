"""Module 4 — Connector Framework API Routes"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_db
from app.models.v2.connector import Connector
from app.models.v2.connector_event import ConnectorEvent
from app.services.v2.connector_framework import get_connector_instance, CONNECTOR_REGISTRY

router = APIRouter()


class ConnectRequest(BaseModel):
    tenant_id: str
    type: str
    name: Optional[str] = None
    credentials: dict = {}
    config: dict = {}


class SyncRequest(BaseModel):
    tenant_id: str
    connector_id: str


class PushRequest(BaseModel):
    tenant_id: str
    connector_id: str
    payload: dict


@router.get("/list")
async def list_connectors(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Connector).where(Connector.tenant_id == tenant_id)
    result = await db.execute(stmt)
    connectors = result.scalars().all()
    return [
        {
            "id": c.id, "type": c.type, "name": c.name, "status": c.status,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in connectors
    ]


@router.get("/available")
async def list_available_connectors():
    """List all available connector types with their implementation status."""
    stubs = {"meta_ads", "tiktok_ads", "youtube_ads"}
    return [
        {
            "type": ctype,
            "implemented": ctype not in stubs,
            "label": ctype.replace("_", " ").title(),
        }
        for ctype in CONNECTOR_REGISTRY
    ]


@router.post("/connect")
async def connect_connector(req: ConnectRequest, db: AsyncSession = Depends(get_db)):
    if req.type not in CONNECTOR_REGISTRY:
        raise HTTPException(400, f"Unknown connector type: {req.type}")

    # Check if connector already exists for this tenant + type
    stmt = select(Connector).where(
        and_(Connector.tenant_id == req.tenant_id, Connector.type == req.type)
    )
    result = await db.execute(stmt)
    connector = result.scalars().first()

    if not connector:
        connector = Connector(
            id=str(uuid.uuid4()),
            tenant_id=req.tenant_id,
            type=req.type,
            name=req.name or req.type.replace("_", " ").title(),
            config_json=req.config,
        )
        db.add(connector)
        await db.flush()

    instance = get_connector_instance(connector, db)
    success = await instance.connect(req.credentials)

    if not success:
        raise HTTPException(400, "Connection failed — check credentials")

    return {"id": connector.id, "type": connector.type, "status": connector.status}


@router.post("/sync")
async def sync_connector(req: SyncRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(Connector).where(
        and_(Connector.id == req.connector_id, Connector.tenant_id == req.tenant_id)
    )
    result = await db.execute(stmt)
    connector = result.scalars().first()
    if not connector:
        raise HTTPException(404, "Connector not found")

    instance = get_connector_instance(connector, db)
    sync_result = await instance.sync()
    return sync_result


@router.post("/push")
async def push_connector(req: PushRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(Connector).where(
        and_(Connector.id == req.connector_id, Connector.tenant_id == req.tenant_id)
    )
    result = await db.execute(stmt)
    connector = result.scalars().first()
    if not connector:
        raise HTTPException(404, "Connector not found")

    instance = get_connector_instance(connector, db)
    push_result = await instance.push(req.payload)
    return push_result


@router.get("/health")
async def connector_health(tenant_id: str, connector_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Connector).where(
        and_(Connector.id == connector_id, Connector.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    connector = result.scalars().first()
    if not connector:
        raise HTTPException(404, "Connector not found")

    instance = get_connector_instance(connector, db)
    return await instance.health_check()


@router.get("/events")
async def connector_events(tenant_id: str, connector_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ConnectorEvent)
        .where(and_(ConnectorEvent.connector_id == connector_id, ConnectorEvent.tenant_id == tenant_id))
        .order_by(ConnectorEvent.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [
        {"id": e.id, "level": e.level, "message": e.message, "payload": e.payload_json, "created_at": e.created_at.isoformat()}
        for e in events
    ]


@router.delete("/{connector_id}")
async def delete_connector(connector_id: str, tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Connector).where(
        and_(Connector.id == connector_id, Connector.tenant_id == tenant_id)
    )
    result = await db.execute(stmt)
    connector = result.scalars().first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    await db.delete(connector)
    return {"deleted": True}
