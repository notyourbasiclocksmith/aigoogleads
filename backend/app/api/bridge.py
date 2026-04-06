"""
CallFlux ↔ IntelliAds Bridge API

Service-to-service endpoints authenticated via X-Bridge-API-Key header.
Allows CallFlux to pull LSA data from IntelliAds and push call insights back.
Allows IntelliAds to pull call data from CallFlux.

Endpoints:
  GET  /api/bridge/lsa/leads          — CallFlux pulls LSA leads for a customer
  GET  /api/bridge/lsa/leads/{id}     — Single LSA lead with conversations
  POST /api/bridge/lsa/leads/{id}/ai  — CallFlux pushes AI analysis results back
  GET  /api/bridge/callflux/calls     — IntelliAds pulls CallFlux call data (proxied)
  GET  /api/bridge/callflux/analytics — IntelliAds pulls CallFlux analytics (proxied)
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import httpx
import logging

from app.core.config import settings
from app.core.database import get_db
from app.models.lsa_lead import LSALead
from app.models.lsa_conversation import LSAConversation

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ──────────────────────────────────────────────────────

def require_bridge_key(
    x_bridge_api_key: str = Header(..., alias="X-Bridge-API-Key"),
) -> str:
    """Validate the shared bridge API key."""
    if not settings.CALLFLUX_BRIDGE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bridge API key not configured",
        )
    if x_bridge_api_key != settings.CALLFLUX_BRIDGE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bridge API key",
        )
    return x_bridge_api_key


# ── Request/Response Models ───────────────────────────────────

class AIAnalysisPayload(BaseModel):
    lead_id: str
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    lead_quality_score: Optional[int] = None
    qualified_lead: Optional[bool] = None
    qualified_reason: Optional[str] = None
    intents: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    transcription_text: Optional[str] = None
    transcription_segments: Optional[List[Dict[str, Any]]] = None
    conversation_id: Optional[str] = None


# ── LSA Endpoints (CallFlux reads from IntelliAds) ────────────

@router.get("/lsa/leads")
async def bridge_list_lsa_leads(
    _key: str = Depends(require_bridge_key),
    db: AsyncSession = Depends(get_db),
    google_customer_id: str = Query(..., description="Google Ads customer ID to filter by"),
    days: int = Query(30, le=90),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    phone_calls_only: bool = Query(False),
):
    """CallFlux pulls LSA leads by google_customer_id (the linking key)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(LSALead).where(
        LSALead.google_customer_id == google_customer_id,
        LSALead.lead_creation_datetime >= cutoff,
    )
    if phone_calls_only:
        stmt = stmt.where(LSALead.lead_type == "PHONE_CALL")

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(desc(LSALead.lead_creation_datetime)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    leads = result.scalars().all()

    return {
        "total": total,
        "leads": [
            {
                "id": l.id,
                "google_lead_id": l.google_lead_id,
                "lead_resource_name": l.lead_resource_name,
                "lead_type": l.lead_type,
                "lead_status": l.lead_status,
                "category_id": l.category_id,
                "service_id": l.service_id,
                "contact_name": l.contact_name,
                "contact_phone": l.contact_phone,
                "contact_email": l.contact_email,
                "lead_charged": l.lead_charged,
                "credit_state": l.credit_state,
                "ai_summary": l.ai_summary,
                "ai_lead_quality_score": l.ai_lead_quality_score,
                "ai_qualified_lead": l.ai_qualified_lead,
                "lead_creation_datetime": l.lead_creation_datetime.isoformat() if l.lead_creation_datetime else None,
                "conversations": [
                    {
                        "id": c.id,
                        "channel": c.channel,
                        "call_duration_ms": c.call_duration_ms,
                        "call_recording_url": c.call_recording_url,
                        "message_text": c.message_text,
                        "event_datetime": c.event_datetime.isoformat() if c.event_datetime else None,
                        "transcription_status": c.transcription_status,
                    }
                    for c in (l.conversations or [])
                ],
            }
            for l in leads
        ],
    }


@router.get("/lsa/leads/{lead_id}")
async def bridge_get_lsa_lead(
    lead_id: str,
    _key: str = Depends(require_bridge_key),
    db: AsyncSession = Depends(get_db),
):
    """Get full LSA lead detail including conversations and transcriptions."""
    result = await db.execute(select(LSALead).where(LSALead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="LSA lead not found")

    return {
        "id": lead.id,
        "google_lead_id": lead.google_lead_id,
        "lead_resource_name": lead.lead_resource_name,
        "lead_type": lead.lead_type,
        "lead_status": lead.lead_status,
        "contact_name": lead.contact_name,
        "contact_phone": lead.contact_phone,
        "contact_email": lead.contact_email,
        "lead_charged": lead.lead_charged,
        "credit_state": lead.credit_state,
        "ai_summary": lead.ai_summary,
        "ai_sentiment": lead.ai_sentiment,
        "ai_lead_quality_score": lead.ai_lead_quality_score,
        "ai_qualified_lead": lead.ai_qualified_lead,
        "ai_qualified_reason": lead.ai_qualified_reason,
        "ai_intents": lead.ai_intents,
        "ai_action_items": lead.ai_action_items,
        "lead_creation_datetime": lead.lead_creation_datetime.isoformat() if lead.lead_creation_datetime else None,
        "conversations": [
            {
                "id": c.id,
                "channel": c.channel,
                "participant_type": c.participant_type,
                "call_duration_ms": c.call_duration_ms,
                "call_recording_url": c.call_recording_url,
                "message_text": c.message_text,
                "event_datetime": c.event_datetime.isoformat() if c.event_datetime else None,
                "transcription_text": c.transcription_text,
                "transcription_status": c.transcription_status,
                "transcription_segments": c.transcription_segments,
            }
            for c in (lead.conversations or [])
        ],
    }


@router.post("/lsa/leads/{lead_id}/ai")
async def bridge_push_ai_analysis(
    lead_id: str,
    payload: AIAnalysisPayload,
    _key: str = Depends(require_bridge_key),
    db: AsyncSession = Depends(get_db),
):
    """CallFlux pushes AI analysis results (transcription, insights) back to IntelliAds."""
    result = await db.execute(select(LSALead).where(LSALead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="LSA lead not found")

    # Update lead-level AI fields
    if payload.summary is not None:
        lead.ai_summary = payload.summary
    if payload.sentiment is not None:
        lead.ai_sentiment = payload.sentiment
    if payload.lead_quality_score is not None:
        lead.ai_lead_quality_score = payload.lead_quality_score
    if payload.qualified_lead is not None:
        lead.ai_qualified_lead = payload.qualified_lead
    if payload.qualified_reason is not None:
        lead.ai_qualified_reason = payload.qualified_reason
    if payload.intents is not None:
        lead.ai_intents = payload.intents
    if payload.action_items is not None:
        lead.ai_action_items = payload.action_items

    # Update conversation-level transcription if specified
    if payload.conversation_id and (payload.transcription_text or payload.transcription_segments):
        conv_result = await db.execute(
            select(LSAConversation).where(
                LSAConversation.id == payload.conversation_id,
                LSAConversation.lead_id == lead_id,
            )
        )
        conv = conv_result.scalar_one_or_none()
        if conv:
            if payload.transcription_text:
                conv.transcription_text = payload.transcription_text
                conv.transcription_status = "succeeded"
            if payload.transcription_segments:
                conv.transcription_segments = payload.transcription_segments

    await db.flush()
    logger.info("Bridge: AI analysis pushed for LSA lead", lead_id=lead_id)
    return {"status": "updated", "lead_id": lead_id}


# ── CallFlux Proxy Endpoints (IntelliAds reads from CallFlux) ─

async def _callflux_request(method: str, path: str, params: dict = None) -> dict:
    """Make an authenticated request to the CallFlux external API."""
    if not settings.CALLFLUX_API_URL or not settings.CALLFLUX_BRIDGE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="CallFlux bridge not configured (set CALLFLUX_API_URL and CALLFLUX_BRIDGE_API_KEY)",
        )

    url = f"{settings.CALLFLUX_API_URL.rstrip('/')}{path}"
    headers = {"X-Internal-API-Key": settings.CALLFLUX_BRIDGE_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.request(method, url, headers=headers, params=params)
        if resp.status_code == 200:
            return resp.json()
        logger.error("CallFlux bridge error", status=resp.status_code, body=resp.text[:300])
        raise HTTPException(status_code=resp.status_code, detail=f"CallFlux API error: {resp.status_code}")
    except httpx.RequestError as e:
        logger.error("CallFlux bridge connection error", error=str(e))
        raise HTTPException(status_code=503, detail=f"CallFlux unreachable: {e}")


@router.get("/callflux/calls")
async def bridge_get_callflux_calls(
    _key: str = Depends(require_bridge_key),
    tenant_id: int = Query(..., description="CallFlux tenant ID"),
    days: int = Query(30),
    page: int = Query(1),
    page_size: int = Query(50),
    qualified_only: bool = Query(False),
):
    """Proxy to CallFlux external API to fetch call data."""
    params = {
        "days": days,
        "page": page,
        "page_size": page_size,
        "qualified_only": qualified_only,
    }
    return await _callflux_request(
        "GET", "/api/external/calls",
        params={**params, "X-Tenant-ID": tenant_id},
    )


@router.get("/callflux/calls/{call_id}")
async def bridge_get_callflux_call_detail(
    call_id: int,
    _key: str = Depends(require_bridge_key),
    tenant_id: int = Query(..., description="CallFlux tenant ID"),
):
    """Proxy to CallFlux to get single call detail with transcription + AI insight."""
    return await _callflux_request(
        "GET", f"/api/external/calls/{call_id}",
        params={"X-Tenant-ID": tenant_id},
    )


@router.get("/callflux/analytics")
async def bridge_get_callflux_analytics(
    _key: str = Depends(require_bridge_key),
    tenant_id: int = Query(..., description="CallFlux tenant ID"),
    days: int = Query(30),
):
    """Proxy to CallFlux analytics summary."""
    return await _callflux_request(
        "GET", "/api/external/analytics",
        params={"days": days, "X-Tenant-ID": tenant_id},
    )


@router.get("/callflux/attribution")
async def bridge_get_callflux_attribution(
    _key: str = Depends(require_bridge_key),
    tenant_id: int = Query(..., description="CallFlux tenant ID"),
    days: int = Query(30),
):
    """Proxy to CallFlux attribution breakdown (Google Ads / DNI)."""
    return await _callflux_request(
        "GET", "/api/external/attribution",
        params={"days": days, "X-Tenant-ID": tenant_id},
    )
