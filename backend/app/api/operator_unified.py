"""
Unified Auto Operator API — single chat experience across Google Ads, Meta Ads, GBP, Image.

Endpoints:
- POST /chat                                Send a chat message (auto-routes to systems)
- POST /chat/new                            Create a new unified conversation
- GET  /chat                                List unified conversations
- GET  /chat/{conversation_id}              Get full conversation
- POST /chat/{conversation_id}/approve      Approve + execute actions
- POST /chat/{conversation_id}/reject       Reject proposed actions
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_tenant
from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.operator_unified import (
    UnifiedChatRequest,
    UnifiedNewConversationRequest,
    UnifiedApproveRequest,
    UnifiedRejectRequest,
    UnifiedChatResponse,
    UnifiedApproveResponse,
)
from app.services.operator_unified.conversation_service import UnifiedConversationService

router = APIRouter()


@router.post("/chat")
async def send_chat_message(
    req: UnifiedChatRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Send a user message. Auto mode classifies intent and queries relevant systems."""
    svc = UnifiedConversationService(db)

    conversation_id = req.conversation_id
    if not conversation_id:
        conv = await svc.create_conversation(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            mode=req.mode.value,
        )
        conversation_id = conv["conversation_id"]

    try:
        result = await svc.chat(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            message=req.message,
            mode=req.mode.value,
            customer_id=req.customer_id,
            date_range=req.date_range,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unified operator error: {str(e)[:300]}")


@router.post("/chat/new")
async def create_conversation(
    req: UnifiedNewConversationRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new unified operator conversation."""
    svc = UnifiedConversationService(db)
    result = await svc.create_conversation(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        mode=req.mode.value,
        title=req.title,
    )
    return result


@router.get("/chat")
async def list_conversations(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all unified conversations for the tenant."""
    svc = UnifiedConversationService(db)
    return await svc.list_conversations(user.tenant_id)


@router.get("/chat/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get full conversation with messages, findings, and proposed actions."""
    svc = UnifiedConversationService(db)
    try:
        return await svc.get_conversation(conversation_id, user.tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/chat/{conversation_id}/approve")
async def approve_actions(
    conversation_id: str,
    req: UnifiedApproveRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve and execute proposed actions across any system."""
    svc = UnifiedConversationService(db)
    try:
        result = await svc.approve_actions(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            action_ids=req.action_ids,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)[:300]}")


@router.post("/chat/{conversation_id}/reject")
async def reject_actions(
    conversation_id: str,
    req: UnifiedRejectRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Reject proposed actions."""
    svc = UnifiedConversationService(db)
    try:
        result = await svc.reject_actions(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            action_ids=req.action_ids,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Session Management ──────────────────────────────────────────

class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.patch("/chat/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    req: RenameConversationRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Rename a conversation."""
    svc = UnifiedConversationService(db)
    try:
        result = await svc.rename_conversation(conversation_id, user.tenant_id, req.title)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/chat/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages/actions."""
    svc = UnifiedConversationService(db)
    try:
        await svc.delete_conversation(conversation_id, user.tenant_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
