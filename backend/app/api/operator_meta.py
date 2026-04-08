"""
Claude Meta Ads Operator API — chat-first Meta Ads control center.

Same pattern as Google Ads operator but uses Meta-specific services.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, require_tenant
from app.services.meta_operator.operator_service import MetaAdsOperatorService

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class MetaChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(..., min_length=1, max_length=5000)


class MetaApproveRequest(BaseModel):
    action_ids: List[str] = Field(..., min_items=1)


class MetaRejectRequest(BaseModel):
    action_ids: List[str] = Field(..., min_items=1)


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/chat")
async def send_chat_message(
    req: MetaChatRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Send a user message and receive Claude's Meta Ads analysis."""
    svc = MetaAdsOperatorService(db)

    conversation_id = req.conversation_id
    if not conversation_id:
        conv = await svc.create_conversation(user.tenant_id, user.user_id)
        conversation_id = conv["conversation_id"]

    try:
        result = await svc.chat(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            message=req.message,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Meta operator error: {str(e)[:300]}")


@router.post("/chat/new")
async def create_conversation(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaAdsOperatorService(db)
    return await svc.create_conversation(user.tenant_id, user.user_id)


@router.get("/chat")
async def list_conversations(
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaAdsOperatorService(db)
    return await svc.list_conversations(user.tenant_id)


@router.get("/chat/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaAdsOperatorService(db)
    try:
        return await svc.get_conversation(conversation_id, user.tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/chat/{conversation_id}/approve")
async def approve_actions(
    conversation_id: str,
    req: MetaApproveRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaAdsOperatorService(db)
    try:
        return await svc.approve_actions(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            action_ids=req.action_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)[:300]}")


@router.post("/chat/{conversation_id}/reject")
async def reject_actions(
    conversation_id: str,
    req: MetaRejectRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    svc = MetaAdsOperatorService(db)
    try:
        return await svc.reject_actions(
            conversation_id=conversation_id,
            tenant_id=user.tenant_id,
            action_ids=req.action_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
