"""
Claude Operator API — chat-first Google Ads control center.

Endpoints:
- POST /chat                               Send a chat message, get Claude analysis
- POST /chat/new                            Create a new conversation
- GET  /chat                                List conversations
- GET  /chat/{conversation_id}              Get full conversation
- POST /chat/{conversation_id}/approve      Approve + execute actions
- POST /chat/{conversation_id}/reject       Reject proposed actions
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_tenant
from app.services.operator.operator_service import GoogleAdsOperatorService

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)
    customer_id: str = Field(..., min_length=1)
    date_range: str = "LAST_30_DAYS"


class NewConversationRequest(BaseModel):
    customer_id: str = Field(..., min_length=1)


class ApproveRequest(BaseModel):
    action_ids: List[str] = Field(..., min_items=1)
    customer_id: str = Field(..., min_length=1)


class RejectRequest(BaseModel):
    action_ids: List[str] = Field(..., min_items=1)


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/chat")
async def send_chat_message(
    req: ChatRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Send a user message and receive Claude's analysis with proposed actions."""
    svc = GoogleAdsOperatorService(db)

    # Auto-create conversation if not provided
    conversation_id = req.conversation_id
    if not conversation_id:
        conv = await svc.create_conversation(user.tenant_id, req.customer_id, user.user_id)
        conversation_id = conv["conversation_id"]

    try:
        result = await svc.chat(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            customer_id=req.customer_id,
            user_id=user.user_id,
            message=req.message,
            date_range=req.date_range,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operator error: {str(e)[:300]}")


@router.post("/chat/new")
async def create_conversation(
    req: NewConversationRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new operator conversation."""
    svc = GoogleAdsOperatorService(db)
    result = await svc.create_conversation(user.tenant_id, req.customer_id, user.user_id)
    return result


@router.get("/chat")
async def list_conversations(
    customer_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for a tenant/account."""
    svc = GoogleAdsOperatorService(db)
    return await svc.list_conversations(user.tenant_id, customer_id)


@router.get("/chat/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get full conversation with messages and proposed actions."""
    svc = GoogleAdsOperatorService(db)
    try:
        return await svc.get_conversation(conversation_id, user.tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/chat/{conversation_id}/approve")
async def approve_actions(
    conversation_id: str,
    req: ApproveRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve and execute proposed actions."""
    svc = GoogleAdsOperatorService(db)
    try:
        result = await svc.approve_actions(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            customer_id=req.customer_id,
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
    req: RejectRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Reject proposed actions."""
    svc = GoogleAdsOperatorService(db)
    try:
        result = await svc.reject_actions(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            action_ids=req.action_ids,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
