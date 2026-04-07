"""
Lead Ingestion API — receives form submissions from FormsAI/BotForms
and records them as leads in IntelliAds.

Webhook flow:
  FormsAI form submitted → POST /api/leads/form-webhook
  → Stores lead in form_leads table
  → Optionally records conversion via revenue attribution
  → Lead appears in Calls & Leads dashboard
"""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Query, Depends
from typing import Optional, List
import structlog
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.landing_page import LandingPageEvent

logger = structlog.get_logger()

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("/form-webhook")
async def form_submission_webhook(
    request: Request,
    tenant_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
):
    """
    Receives form submissions from FormsAI/BotForms.
    This is a PUBLIC endpoint (no auth) — FormsAI posts here on each submission.

    FormsAI webhook payload:
    {
        "form_id": "endpoint",
        "submission_id": "uuid",
        "data": {
            "full_name": "John Doe",
            "phone": "+15551234567",
            "email": "john@example.com",
            "service_needed": "Emergency Repair",
            "description": "...",
        },
        "response_url": "https://botforms.ai/view/{token}",
        "submitted_at": "ISO_8601"
    }
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "message": "Invalid JSON payload"}

    data = payload.get("data", {})
    submission_id = payload.get("submission_id", "")
    form_id = payload.get("form_id", "")
    submitted_at = payload.get("submitted_at", "")

    # Extract lead info from the form data
    lead_name = (
        data.get("full_name")
        or data.get("name")
        or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        or "Unknown"
    )
    lead_phone = data.get("phone") or data.get("phone_number") or ""
    lead_email = data.get("email") or data.get("email_address") or ""
    service_needed = data.get("service_needed") or data.get("service") or ""

    logger.info(
        "Form lead received from FormsAI",
        form_id=form_id,
        submission_id=submission_id,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        lead_name=lead_name,
        lead_phone=lead_phone,
        service_needed=service_needed,
    )

    # Store in landing_page_events (with nullable landing_page_id for webhook leads)
    if tenant_id:
        try:
            from app.core.database import async_session_factory
            async with async_session_factory() as db:
                event = LandingPageEvent(
                    id=str(uuid.uuid4()),
                    landing_page_id=None,  # Will be linked if we can resolve it
                    event_type="form_submit",
                    metadata_json={
                        "source": "formsai_webhook",
                        "tenant_id": tenant_id,
                        "form_id": form_id,
                        "submission_id": submission_id,
                        "campaign_id": campaign_id,
                        "lead_name": lead_name,
                        "lead_phone": lead_phone,
                        "lead_email": lead_email,
                        "service_needed": service_needed,
                        "full_data": data,
                        "response_url": payload.get("response_url", ""),
                        "submitted_at": submitted_at,
                    },
                )
                db.add(event)
                await db.commit()
        except Exception as e:
            logger.error("Failed to store form lead event", error=str(e))

    return {
        "status": "ok",
        "message": "Lead received",
        "submission_id": submission_id,
    }


@router.get("/form-leads")
async def list_form_leads(
    db: AsyncSession = Depends(get_db),
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    List form leads for a tenant (from FormsAI webhook submissions).
    Used by the Calls & Leads dashboard.
    """
    query = (
        select(LandingPageEvent)
        .where(LandingPageEvent.event_type == "form_submit")
        .order_by(desc(LandingPageEvent.created_at))
    )

    if tenant_id:
        # Filter by tenant via metadata_json
        from sqlalchemy import cast, String
        query = query.where(
            LandingPageEvent.metadata_json["tenant_id"].astext == tenant_id
        )

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    events = result.scalars().all()

    leads = []
    for event in events:
        meta = event.metadata_json or {}
        leads.append({
            "id": event.id,
            "lead_name": meta.get("lead_name", "Unknown"),
            "lead_phone": meta.get("lead_phone", ""),
            "lead_email": meta.get("lead_email", ""),
            "service_needed": meta.get("service_needed", ""),
            "campaign_id": meta.get("campaign_id"),
            "form_id": meta.get("form_id", ""),
            "submission_id": meta.get("submission_id", ""),
            "response_url": meta.get("response_url", ""),
            "source": "formsai",
            "created_at": event.created_at.isoformat() if event.created_at else None,
        })

    return {"leads": leads, "total": len(leads), "limit": limit, "offset": offset}
