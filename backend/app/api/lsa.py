"""
LSA (Local Services Ads) API — leads, conversations, recordings, disputes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser
from app.models.lsa_lead import LSALead
from app.models.lsa_conversation import LSAConversation
from app.models.integration_google_ads import IntegrationGoogleAds

router = APIRouter()


# ── List LSA Leads ────────────────────────────────────────────

@router.get("/leads")
async def list_lsa_leads(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    lead_type: Optional[str] = Query(None, description="Filter: PHONE_CALL, MESSAGE, BOOKING"),
    lead_status: Optional[str] = Query(None),
    charged_only: bool = Query(False),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """List all LSA leads for this tenant with optional filters."""
    stmt = select(LSALead).where(LSALead.tenant_id == user.tenant_id)

    if lead_type:
        stmt = stmt.where(LSALead.lead_type == lead_type)
    if lead_status:
        stmt = stmt.where(LSALead.lead_status == lead_status)
    if charged_only:
        stmt = stmt.where(LSALead.lead_charged == True)

    # Count
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
                "lead_type": l.lead_type,
                "category_id": l.category_id,
                "service_id": l.service_id,
                "lead_status": l.lead_status,
                "contact_name": l.contact_name,
                "contact_phone": l.contact_phone,
                "contact_email": l.contact_email,
                "lead_charged": l.lead_charged,
                "credit_state": l.credit_state,
                "feedback_submitted": l.feedback_submitted,
                "ai_summary": l.ai_summary,
                "ai_sentiment": l.ai_sentiment,
                "ai_lead_quality_score": l.ai_lead_quality_score,
                "ai_qualified_lead": l.ai_qualified_lead,
                "lead_creation_datetime": l.lead_creation_datetime.isoformat() if l.lead_creation_datetime else None,
                "synced_at": l.synced_at.isoformat() if l.synced_at else None,
                "conversations": [
                    {
                        "id": c.id,
                        "channel": c.channel,
                        "participant_type": c.participant_type,
                        "event_datetime": c.event_datetime.isoformat() if c.event_datetime else None,
                        "call_duration_ms": c.call_duration_ms,
                        "call_recording_url": c.call_recording_url,
                        "message_text": c.message_text,
                        "transcription_status": c.transcription_status,
                        "has_transcription": bool(c.transcription_text),
                    }
                    for c in (l.conversations or [])
                ],
            }
            for l in leads
        ],
    }


# ── Single LSA Lead Detail ───────────────────────────────────

@router.get("/leads/{lead_id}")
async def get_lsa_lead(
    lead_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get full detail for a single LSA lead including conversations and AI insights."""
    result = await db.execute(
        select(LSALead).where(
            LSALead.id == lead_id,
            LSALead.tenant_id == user.tenant_id,
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="LSA lead not found")

    return {
        "id": lead.id,
        "google_lead_id": lead.google_lead_id,
        "lead_resource_name": lead.lead_resource_name,
        "lead_type": lead.lead_type,
        "category_id": lead.category_id,
        "service_id": lead.service_id,
        "lead_status": lead.lead_status,
        "locale": lead.locale,
        "contact_name": lead.contact_name,
        "contact_phone": lead.contact_phone,
        "contact_email": lead.contact_email,
        "lead_charged": lead.lead_charged,
        "credit_state": lead.credit_state,
        "feedback_submitted": lead.feedback_submitted,
        "feedback_json": lead.feedback_json,
        "ai_summary": lead.ai_summary,
        "ai_sentiment": lead.ai_sentiment,
        "ai_lead_quality_score": lead.ai_lead_quality_score,
        "ai_qualified_lead": lead.ai_qualified_lead,
        "ai_qualified_reason": lead.ai_qualified_reason,
        "ai_intents": lead.ai_intents,
        "ai_action_items": lead.ai_action_items,
        "lead_creation_datetime": lead.lead_creation_datetime.isoformat() if lead.lead_creation_datetime else None,
        "synced_at": lead.synced_at.isoformat() if lead.synced_at else None,
        "conversations": [
            {
                "id": c.id,
                "channel": c.channel,
                "participant_type": c.participant_type,
                "event_datetime": c.event_datetime.isoformat() if c.event_datetime else None,
                "call_duration_ms": c.call_duration_ms,
                "call_duration_formatted": _format_duration(c.call_duration_ms),
                "call_recording_url": c.call_recording_url,
                "message_text": c.message_text,
                "attachment_urls": c.attachment_urls,
                "transcription_text": c.transcription_text,
                "transcription_status": c.transcription_status,
                "transcription_segments": c.transcription_segments,
            }
            for c in (lead.conversations or [])
        ],
    }


# ── LSA Dashboard Summary ────────────────────────────────────

@router.get("/summary")
async def lsa_summary(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, le=90),
):
    """Get LSA summary stats: total leads, calls, messages, charged, disputed, AI-qualified."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    base = select(LSALead).where(
        LSALead.tenant_id == user.tenant_id,
        LSALead.lead_creation_datetime >= cutoff,
    )

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar() or 0

    calls_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.lead_type == "PHONE_CALL").subquery()
        )
    )
    calls = calls_result.scalar() or 0

    messages_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.lead_type == "MESSAGE").subquery()
        )
    )
    messages = messages_result.scalar() or 0

    charged_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.lead_charged == True).subquery()
        )
    )
    charged = charged_result.scalar() or 0

    disputed_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.feedback_submitted == True).subquery()
        )
    )
    disputed = disputed_result.scalar() or 0

    credited_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.credit_state == "CREDITED").subquery()
        )
    )
    credited = credited_result.scalar() or 0

    ai_qualified_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.ai_qualified_lead == True).subquery()
        )
    )
    ai_qualified = ai_qualified_result.scalar() or 0

    ai_spam_result = await db.execute(
        select(func.count()).select_from(
            base.where(LSALead.ai_qualified_lead == False).subquery()
        )
    )
    ai_spam = ai_spam_result.scalar() or 0

    # Average AI lead quality score
    avg_score_result = await db.execute(
        select(func.avg(LSALead.ai_lead_quality_score)).where(
            LSALead.tenant_id == user.tenant_id,
            LSALead.lead_creation_datetime >= cutoff,
            LSALead.ai_lead_quality_score.isnot(None),
        )
    )
    avg_quality = avg_score_result.scalar()

    return {
        "period_days": days,
        "total_leads": total,
        "phone_calls": calls,
        "messages": messages,
        "bookings": total - calls - messages,
        "charged_leads": charged,
        "disputed_leads": disputed,
        "credited_leads": credited,
        "ai_qualified_leads": ai_qualified,
        "ai_spam_leads": ai_spam,
        "ai_pending_analysis": total - ai_qualified - ai_spam,
        "avg_ai_quality_score": round(avg_quality, 1) if avg_quality else None,
    }


# ── Dispute / Feedback ───────────────────────────────────────

class DisputeRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/leads/{lead_id}/dispute")
async def dispute_lsa_lead(
    lead_id: str,
    req: DisputeRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Dispute an LSA lead to request a credit from Google."""
    result = await db.execute(
        select(LSALead).where(
            LSALead.id == lead_id,
            LSALead.tenant_id == user.tenant_id,
        )
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="LSA lead not found")

    if lead.feedback_submitted:
        raise HTTPException(status_code=400, detail="Feedback already submitted for this lead")

    if not lead.lead_charged:
        raise HTTPException(status_code=400, detail="Cannot dispute a lead that wasn't charged")

    # Get integration for API call
    integ_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.customer_id == lead.google_customer_id,
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = integ_result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=400, detail="No active Google Ads integration found")

    from app.integrations.google_ads.client import GoogleAdsClient
    client = GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token_encrypted=integration.refresh_token_encrypted,
        login_customer_id=integration.login_customer_id,
    )

    result = await client.submit_lsa_lead_feedback(lead.lead_resource_name, "DISPUTE")

    if result.get("status") == "submitted":
        lead.feedback_submitted = True
        lead.feedback_json = {
            "type": "DISPUTE",
            "reason": req.reason,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "submitted_by": user.user_id,
        }
        await db.flush()
        return {"status": "disputed", "lead_id": lead_id}

    raise HTTPException(status_code=500, detail=result.get("error", "Failed to submit dispute"))


# ── Force Sync LSA ────────────────────────────────────────────

@router.post("/sync")
async def trigger_lsa_sync(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a manual LSA sync for this tenant."""
    integ_result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        ).limit(1)
    )
    integration = integ_result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=400, detail="No active Google Ads integration")

    from app.integrations.google_ads.client import GoogleAdsClient
    client = GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token_encrypted=integration.refresh_token_encrypted,
        login_customer_id=integration.login_customer_id,
    )

    # Sync leads
    lsa_leads = await client.get_lsa_leads(days=30)
    lead_count = 0
    lsa_resource_to_uuid = {}
    for ll in lsa_leads:
        existing = await db.execute(
            select(LSALead).where(
                LSALead.tenant_id == user.tenant_id,
                LSALead.google_lead_id == ll["lead_id"],
            )
        )
        lead_obj = existing.scalar_one_or_none()
        if not lead_obj:
            lead_obj = LSALead(
                tenant_id=user.tenant_id,
                google_customer_id=integration.customer_id,
                lead_resource_name=ll["resource_name"],
                google_lead_id=ll["lead_id"],
                lead_type=ll["lead_type"],
                category_id=ll.get("category_id"),
                service_id=ll.get("service_id"),
                lead_status=ll.get("lead_status"),
                locale=ll.get("locale"),
                contact_name=ll.get("contact_name"),
                contact_phone=ll.get("contact_phone"),
                contact_email=ll.get("contact_email"),
                lead_charged=ll.get("lead_charged", False),
                credit_state=ll.get("credit_state"),
                lead_creation_datetime=ll.get("creation_date_time"),
                synced_at=datetime.now(timezone.utc),
            )
            db.add(lead_obj)
            await db.flush()
        else:
            lead_obj.lead_status = ll.get("lead_status") or lead_obj.lead_status
            lead_obj.lead_charged = ll.get("lead_charged", lead_obj.lead_charged)
            lead_obj.credit_state = ll.get("credit_state") or lead_obj.credit_state
            lead_obj.synced_at = datetime.now(timezone.utc)
        lsa_resource_to_uuid[ll["resource_name"]] = lead_obj.id
        lead_count += 1

    # Sync conversations
    convos = await client.get_lsa_conversations(days=30)
    conv_count = 0
    for lc in convos:
        lead_rn = lc.get("lead_resource_name", "")
        parent_uuid = lsa_resource_to_uuid.get(lead_rn)
        if not parent_uuid:
            lookup = await db.execute(select(LSALead).where(LSALead.lead_resource_name == lead_rn))
            found = lookup.scalar_one_or_none()
            if found:
                parent_uuid = found.id
            else:
                continue

        existing_lc = await db.execute(
            select(LSAConversation).where(
                LSAConversation.conversation_resource_name == lc["resource_name"],
            )
        )
        conv_obj = existing_lc.scalar_one_or_none()
        if not conv_obj:
            conv_obj = LSAConversation(
                tenant_id=user.tenant_id,
                lead_id=parent_uuid,
                conversation_resource_name=lc["resource_name"],
                channel=lc["channel"],
                participant_type=lc.get("participant_type"),
                event_datetime=lc.get("event_date_time"),
                call_duration_ms=lc.get("call_duration_ms"),
                call_recording_url=lc.get("call_recording_url"),
                message_text=lc.get("message_text"),
                attachment_urls=lc.get("attachment_urls"),
                synced_at=datetime.now(timezone.utc),
            )
            db.add(conv_obj)
        conv_count += 1

    await db.flush()
    return {"status": "synced", "leads": lead_count, "conversations": conv_count}


# ── Helpers ───────────────────────────────────────────────────

def _format_duration(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    seconds = ms // 1000
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}:{secs:02d}"
