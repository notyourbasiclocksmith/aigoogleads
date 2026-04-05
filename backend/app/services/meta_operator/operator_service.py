"""
Meta Ads Operator Service — orchestrates the full read → analyze → propose → execute flow.

Reuses the same OperatorConversation/OperatorMessage/ProposedAction models as Google Ads,
differentiated by the customer_id field (Meta ad account ID).
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.operator import OperatorConversation, OperatorMessage, ProposedAction, ActionExecutionLog
from app.models.v2.integration_meta import IntegrationMeta
from app.integrations.meta_ads.client import MetaAdsClient
from app.services.meta_operator.context_service import MetaAdsContextService
from app.services.meta_operator.mutation_service import MetaAdsMutationService
from app.services.meta_operator.claude_agent_service import ClaudeMetaAgentService

logger = structlog.get_logger()


class MetaAdsOperatorService:
    """Orchestrates the Claude Meta Ads Operator chat flow."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.claude = ClaudeMetaAgentService()

    async def _get_meta_client(self, tenant_id: str) -> MetaAdsClient:
        """Get an authenticated Meta Ads client for a tenant."""
        result = await self.db.execute(
            select(IntegrationMeta).where(IntegrationMeta.tenant_id == tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            raise ValueError("No Meta Ads integration found for this tenant")
        return MetaAdsClient(
            ad_account_id=integration.ad_account_id,
            access_token_encrypted=integration.access_token_encrypted,
        )

    # ── CONVERSATION MANAGEMENT ────────────────────────���─────────

    async def create_conversation(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        conv = OperatorConversation(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            customer_id=f"meta_{tenant_id}",
            created_by=user_id,
            title="New Meta Ads conversation",
        )
        self.db.add(conv)
        await self.db.flush()
        return {"conversation_id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat()}

    async def list_conversations(self, tenant_id: str) -> List[Dict[str, Any]]:
        result = await self.db.execute(
            select(OperatorConversation)
            .where(
                and_(
                    OperatorConversation.tenant_id == tenant_id,
                    OperatorConversation.customer_id == f"meta_{tenant_id}",
                )
            )
            .order_by(OperatorConversation.updated_at.desc())
            .limit(50)
        )
        convos = result.scalars().all()
        return [
            {
                "conversation_id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in convos
        ]

    # ── CHAT ─────────────────────────────────────────────────────

    async def chat(
        self,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        message: str,
    ) -> Dict[str, Any]:
        """Process a user chat message for Meta Ads."""

        result = await self.db.execute(
            select(OperatorConversation).where(
                and_(
                    OperatorConversation.id == conversation_id,
                    OperatorConversation.tenant_id == tenant_id,
                )
            )
        )
        conv = result.scalars().first()
        if not conv:
            raise ValueError("Conversation not found")

        # Save user message
        user_msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="user",
            content=message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        # Update title on first message
        msg_count_result = await self.db.execute(
            select(OperatorMessage).where(
                and_(
                    OperatorMessage.conversation_id == conversation_id,
                    OperatorMessage.role == "user",
                )
            )
        )
        if len(msg_count_result.scalars().all()) == 1:
            conv.title = message[:100]

        # Get Meta Ads client + context
        meta_client = await self._get_meta_client(tenant_id)
        context_svc = MetaAdsContextService(meta_client)
        account_context = await context_svc.build_full_context()

        # Conversation history
        history_result = await self.db.execute(
            select(OperatorMessage)
            .where(OperatorMessage.conversation_id == conversation_id)
            .order_by(OperatorMessage.created_at)
        )
        all_msgs = history_result.scalars().all()
        conversation_history = []
        for m in all_msgs:
            if m.role in ("user", "assistant"):
                content = m.content or ""
                if m.structured_payload and m.structured_payload.get("summary"):
                    content = m.structured_payload["summary"]
                conversation_history.append({"role": m.role, "content": content})

        # Call Claude
        claude_response = await self.claude.analyze(
            user_message=message,
            account_context=account_context,
            conversation_history=conversation_history[:-1],
        )

        # Save assistant message
        assistant_msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=claude_response.get("summary", ""),
            structured_payload=claude_response,
        )
        self.db.add(assistant_msg)
        await self.db.flush()

        # Save proposed actions
        proposed_actions = []
        for action in claude_response.get("recommended_actions", []):
            pa = ProposedAction(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                message_id=assistant_msg.id,
                action_type=action["action_type"],
                label=action.get("label", action["action_type"]),
                reasoning=action.get("reasoning"),
                expected_impact=action.get("expected_impact"),
                risk_level=action.get("risk_level", "medium"),
                action_payload=action.get("action_payload", {}),
                status="proposed",
            )
            self.db.add(pa)
            proposed_actions.append({
                "id": pa.id,
                "action_type": pa.action_type,
                "label": pa.label,
                "reasoning": pa.reasoning,
                "expected_impact": pa.expected_impact,
                "risk_level": pa.risk_level,
                "status": pa.status,
                "action_payload": pa.action_payload,
            })

        conv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return {
            "conversation_id": conversation_id,
            "message_id": assistant_msg.id,
            "summary": claude_response.get("summary", ""),
            "findings": claude_response.get("findings", []),
            "recommended_actions": proposed_actions,
            "questions": claude_response.get("questions", []),
            "message": claude_response.get("message", ""),
        }

    # ── APPROVE / REJECT ──────────────────────────────────────────

    async def approve_actions(
        self,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        action_ids: List[str],
    ) -> Dict[str, Any]:
        conv_result = await self.db.execute(
            select(OperatorConversation).where(
                and_(
                    OperatorConversation.id == conversation_id,
                    OperatorConversation.tenant_id == tenant_id,
                )
            )
        )
        conv = conv_result.scalars().first()
        if not conv:
            raise ValueError("Conversation not found")

        result = await self.db.execute(
            select(ProposedAction).where(
                and_(
                    ProposedAction.conversation_id == conversation_id,
                    ProposedAction.id.in_(action_ids),
                    ProposedAction.status == "proposed",
                )
            )
        )
        actions = result.scalars().all()
        if not actions:
            return {"status": "no_actions", "message": "No pending actions found to approve"}

        meta_client = await self._get_meta_client(tenant_id)
        mutation_svc = MetaAdsMutationService(meta_client)

        execution_results = []
        now = datetime.now(timezone.utc)

        for action in actions:
            action.status = "approved"
            action.approved_at = now
            action.executed_by = user_id

            try:
                exec_result = await mutation_svc.execute_action(
                    action.action_type, action.action_payload
                )
                exec_status = exec_result.get("status", "failed")
                action.status = "executed" if exec_status == "success" else "failed"
                action.executed_at = datetime.now(timezone.utc)

                log = ActionExecutionLog(
                    id=str(uuid.uuid4()),
                    proposed_action_id=action.id,
                    tenant_id=tenant_id,
                    customer_id=f"meta_{tenant_id}",
                    request_payload=action.action_payload,
                    response_payload=exec_result,
                    status=exec_status,
                    error_message=exec_result.get("error"),
                )
                self.db.add(log)

                execution_results.append({
                    "action_id": action.id,
                    "action_type": action.action_type,
                    "label": action.label,
                    "status": exec_status,
                    "details": exec_result,
                })
            except Exception as e:
                action.status = "failed"
                action.executed_at = datetime.now(timezone.utc)
                log = ActionExecutionLog(
                    id=str(uuid.uuid4()),
                    proposed_action_id=action.id,
                    tenant_id=tenant_id,
                    customer_id=f"meta_{tenant_id}",
                    request_payload=action.action_payload,
                    status="failed",
                    error_message=str(e)[:1000],
                )
                self.db.add(log)
                execution_results.append({
                    "action_id": action.id,
                    "action_type": action.action_type,
                    "label": action.label,
                    "status": "failed",
                    "error": str(e)[:200],
                })

        succeeded = sum(1 for r in execution_results if r["status"] == "success")
        failed = sum(1 for r in execution_results if r["status"] != "success")

        exec_msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=f"Executed {succeeded} action(s) successfully. {failed} failed." if failed else f"All {succeeded} action(s) executed successfully.",
            structured_payload={"type": "execution_result", "results": execution_results, "succeeded": succeeded, "failed": failed},
        )
        self.db.add(exec_msg)
        conv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return {"status": "completed", "succeeded": succeeded, "failed": failed, "results": execution_results}

    async def reject_actions(
        self, conversation_id: str, tenant_id: str, action_ids: List[str],
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(ProposedAction).where(
                and_(
                    ProposedAction.conversation_id == conversation_id,
                    ProposedAction.id.in_(action_ids),
                    ProposedAction.status == "proposed",
                )
            )
        )
        actions = result.scalars().all()
        for action in actions:
            action.status = "rejected"
        await self.db.flush()
        return {"status": "rejected", "count": len(actions)}
