"""
Audit Logging Service — records security-relevant events.
"""
import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_event import AuditEvent


async def log_event(
    db: AsyncSession,
    event_type: str,
    severity: str = "info",
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditEvent:
    event = AuditEvent(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        severity=severity,
        metadata_json=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(event)
    return event
