"""
Unified Conversation Service — orchestrates the full multi-system operator flow.

Flow: intent_router → context_builder → agent_service → store results
Handles conversation CRUD, chat, approve, reject across all systems.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case

from app.models.operator import (
    OperatorConversation, OperatorMessage, ProposedAction, ActionExecutionLog,
)
from app.services.operator_unified.intent_router import classify_intent
from app.services.operator_unified.context_builder import UnifiedContextBuilder
from app.services.operator_unified.agent_service import UnifiedAgentService
from app.services.operator_unified.action_router import ActionRouter
from app.services.operator.campaign_agent_pipeline import CampaignAgentPipeline
from app.services.operator.post_execution_audit import PostExecutionAuditAgent

logger = structlog.get_logger()


class UnifiedConversationService:
    """Orchestrates the Unified Auto Operator chat flow across all systems."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = UnifiedAgentService()

    # ── CONVERSATION MANAGEMENT ──────────────────────────────────

    async def create_conversation(
        self, tenant_id: str, user_id: str, mode: str = "auto", title: Optional[str] = None,
    ) -> Dict[str, Any]:
        conv = OperatorConversation(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            customer_id=f"unified_{tenant_id}",
            created_by=user_id,
            title=title or "New conversation",
            mode=mode,
        )
        self.db.add(conv)
        await self.db.flush()
        return {
            "conversation_id": conv.id,
            "title": conv.title,
            "mode": mode,
            "created_at": conv.created_at.isoformat(),
        }

    async def list_conversations(self, tenant_id: str) -> List[Dict[str, Any]]:
        # Get conversations with action stats in a single query
        stmt = (
            select(
                OperatorConversation,
                func.count(ProposedAction.id).label("total_actions"),
                func.sum(case((ProposedAction.status == "executed", 1), else_=0)).label("executed_actions"),
                func.sum(case((ProposedAction.status == "failed", 1), else_=0)).label("failed_actions"),
            )
            .outerjoin(ProposedAction, ProposedAction.conversation_id == OperatorConversation.id)
            .where(OperatorConversation.tenant_id == tenant_id)
            .group_by(OperatorConversation.id)
            .order_by(OperatorConversation.updated_at.desc())
            .limit(50)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        return [
            {
                "conversation_id": c.id,
                "title": c.title,
                "mode": c.mode or "auto",
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
                "actions_executed": int(executed or 0),
                "actions_failed": int(failed or 0),
                "actions_total": int(total or 0),
            }
            for c, total, executed, failed in rows
        ]

    async def rename_conversation(self, conversation_id: str, tenant_id: str, title: str) -> Dict[str, Any]:
        result = await self.db.execute(
            select(OperatorConversation).where(
                and_(
                    OperatorConversation.id == conversation_id,
                    OperatorConversation.tenant_id == tenant_id,
                )
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise ValueError("Conversation not found")
        conv.title = title
        await self.db.flush()
        return {"conversation_id": conv.id, "title": conv.title}

    async def delete_conversation(self, conversation_id: str, tenant_id: str) -> None:
        result = await self.db.execute(
            select(OperatorConversation).where(
                and_(
                    OperatorConversation.id == conversation_id,
                    OperatorConversation.tenant_id == tenant_id,
                )
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise ValueError("Conversation not found")
        await self.db.delete(conv)
        await self.db.flush()

    async def get_conversation(self, conversation_id: str, tenant_id: str) -> Dict[str, Any]:
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

        msg_result = await self.db.execute(
            select(OperatorMessage)
            .where(OperatorMessage.conversation_id == conversation_id)
            .order_by(OperatorMessage.created_at)
        )
        messages = msg_result.scalars().all()

        action_result = await self.db.execute(
            select(ProposedAction)
            .where(ProposedAction.conversation_id == conversation_id)
            .order_by(ProposedAction.created_at)
        )
        actions = action_result.scalars().all()
        actions_by_msg: Dict[str, list] = {}
        for a in actions:
            actions_by_msg.setdefault(a.message_id, []).append({
                "id": a.id,
                "system": (a.action_payload or {}).get("_system", "google_ads"),
                "action_type": a.action_type,
                "label": a.label,
                "reasoning": a.reasoning,
                "expected_impact": a.expected_impact,
                "risk_level": a.risk_level,
                "status": a.status,
                "action_payload": a.action_payload,
            })

        return {
            "conversation_id": conv.id,
            "title": conv.title,
            "mode": conv.mode or "auto",
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "structured_payload": m.structured_payload,
                    "proposed_actions": actions_by_msg.get(m.id, []),
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }

    # ── CHAT ─────────────────────────────────────────────────────

    async def chat(
        self,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        message: str,
        mode: str = "auto",
        customer_id: Optional[str] = None,
        date_range: str = "LAST_30_DAYS",
    ) -> Dict[str, Any]:
        """
        Full chat flow:
        1. Save user message
        2. Classify intent → determine target systems
        3. Build multi-system context
        4. Call unified Claude agent
        5. Store results + proposed actions
        """
        # Validate conversation ownership
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

        # Update title on first user message
        msg_count_result = await self.db.execute(
            select(OperatorMessage).where(
                and_(
                    OperatorMessage.conversation_id == conversation_id,
                    OperatorMessage.role == "user",
                )
            )
        )
        user_msgs = msg_count_result.scalars().all()
        if len(user_msgs) == 1:
            conv.title = message[:100]

        # 1. Classify intent
        systems = classify_intent(message, mode)
        logger.info("unified_intent", systems=systems, mode=mode, msg=message[:80])

        # 2. Build multi-system context
        ctx_builder = UnifiedContextBuilder(self.db, tenant_id)
        context = await ctx_builder.build(systems, customer_id=customer_id, date_range=date_range)

        # 3. Get conversation history
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

        # 4. Call unified Claude agent
        claude_response = await self.agent.analyze(
            user_message=message,
            context=context,
            systems_used=context.get("connected_systems", systems),
            conversation_history=conversation_history[:-1],
        )

        # 4b. Pipeline intercept — if Claude recommends deploy_full_campaign, run multi-agent pipeline
        has_campaign_deploy = any(
            a.get("action_type") == "deploy_full_campaign"
            for a in claude_response.get("recommended_actions", [])
        )
        if has_campaign_deploy and customer_id:
            try:
                pipeline = CampaignAgentPipeline(self.db, tenant_id, customer_id)
                pipeline_spec = await pipeline.run(
                    user_prompt=message,
                    account_context=context.get("google_ads", {}),
                    conversation_id=conversation_id,
                )
                for action in claude_response.get("recommended_actions", []):
                    if action.get("action_type") == "deploy_full_campaign":
                        action["payload"] = pipeline_spec
                        action["action_payload"] = pipeline_spec
                        action["label"] = f"Deploy Campaign: {pipeline_spec.get('campaign', {}).get('name', 'AI Campaign')}"
                        meta = pipeline_spec.get("_pipeline_metadata", {})
                        qa_score = meta.get("qa_score")
                        if qa_score:
                            action["reasoning"] = f"{action.get('reasoning', '')} [Pipeline QA Score: {qa_score}/100]".strip()
            except Exception as e:
                logger.error("Unified pipeline intercept failed", error=str(e))

        # 5. Save assistant message
        assistant_msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=claude_response.get("summary", ""),
            structured_payload={
                **claude_response,
                "_systems_used": context.get("connected_systems", systems),
                "_system_errors": context.get("system_errors", {}),
            },
        )
        self.db.add(assistant_msg)
        await self.db.flush()

        # 6. Save proposed actions with system tag
        proposed_actions = []
        for action in claude_response.get("recommended_actions", []):
            system = action.get("system", "google_ads")
            payload = action.get("payload", {})
            payload["_system"] = system  # Tag for routing during execution

            pa = ProposedAction(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                message_id=assistant_msg.id,
                action_type=action.get("action_type", "unknown"),
                label=action.get("label", action.get("action_type", "Action")),
                reasoning=action.get("reasoning"),
                expected_impact=action.get("expected_impact"),
                risk_level=action.get("risk_level", "medium"),
                action_payload=payload,
                status="proposed",
            )
            self.db.add(pa)
            proposed_actions.append({
                "id": pa.id,
                "system": system,
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

        # Build connected systems status
        connected_systems = []
        for s in systems:
            error = context.get("system_errors", {}).get(s)
            connected_systems.append({
                "name": s,
                "connected": s in context.get("connected_systems", []),
                "error": error,
            })

        return {
            "conversation_id": conversation_id,
            "message_id": assistant_msg.id,
            "mode": mode,
            "systems_used": context.get("connected_systems", systems),
            "summary": claude_response.get("summary", ""),
            "findings": claude_response.get("findings", []),
            "recommended_actions": proposed_actions,
            "questions": claude_response.get("questions", []),
            "message": claude_response.get("message", ""),
            "connected_systems": connected_systems,
        }

    # ── APPROVE / REJECT ─────────────────────────────────────────

    async def approve_actions(
        self,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        action_ids: List[str],
    ) -> Dict[str, Any]:
        """Approve and execute actions via the unified action router."""

        # Validate conversation
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

        # Get pending actions
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
            return {"status": "no_actions", "succeeded": 0, "failed": 0, "results": []}

        router = ActionRouter(self.db, tenant_id)
        execution_results = []
        now = datetime.now(timezone.utc)

        for action in actions:
            action.status = "approved"
            action.approved_at = now
            action.executed_by = user_id

            payload = dict(action.action_payload or {})
            system = payload.pop("_system", "google_ads")

            try:
                exec_result = await router.execute(system, action.action_type, payload)

                exec_status = exec_result.get("status", "failed")
                action.status = "executed" if exec_status == "success" else "failed"
                action.executed_at = datetime.now(timezone.utc)

                log = ActionExecutionLog(
                    id=str(uuid.uuid4()),
                    proposed_action_id=action.id,
                    tenant_id=tenant_id,
                    customer_id=f"unified_{tenant_id}",
                    request_payload=action.action_payload,
                    response_payload=exec_result,
                    before_state=exec_result.get("before"),
                    after_state=exec_result.get("after"),
                    status=exec_status,
                    error_message=exec_result.get("error"),
                )
                self.db.add(log)

                execution_results.append({
                    "action_id": action.id,
                    "system": system,
                    "action_type": action.action_type,
                    "status": exec_status,
                    "summary": exec_result.get("summary", ""),
                    "details": exec_result.get("details"),
                    "before": exec_result.get("before"),
                    "after": exec_result.get("after"),
                    "error": exec_result.get("error"),
                })
            except Exception as e:
                action.status = "failed"
                action.executed_at = datetime.now(timezone.utc)

                log = ActionExecutionLog(
                    id=str(uuid.uuid4()),
                    proposed_action_id=action.id,
                    tenant_id=tenant_id,
                    customer_id=f"unified_{tenant_id}",
                    request_payload=action.action_payload,
                    status="failed",
                    error_message=str(e)[:1000],
                )
                self.db.add(log)

                execution_results.append({
                    "action_id": action.id,
                    "system": system,
                    "action_type": action.action_type,
                    "status": "failed",
                    "summary": "Execution failed",
                    "error": str(e)[:200],
                })

        # Save execution result message
        succeeded = sum(1 for r in execution_results if r["status"] == "success")
        failed = sum(1 for r in execution_results if r["status"] != "success")

        exec_msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=(
                f"All {succeeded} action(s) executed successfully."
                if not failed
                else f"Executed {succeeded} action(s) successfully. {failed} failed."
            ),
            structured_payload={
                "type": "execution_result",
                "results": execution_results,
                "succeeded": succeeded,
                "failed": failed,
            },
        )
        self.db.add(exec_msg)
        conv.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        # ── POST-EXECUTION AUDIT for deploy_full_campaign ──
        audit_result = None
        for action in actions:
            if action.action_type != "deploy_full_campaign":
                continue
            payload = dict(action.action_payload or {})
            system = payload.pop("_system", "google_ads")
            if system != "google_ads":
                continue
            exec_res = next(
                (r for r in execution_results
                 if r["action_id"] == action.id and r["status"] in ("success", "partial")),
                None,
            )
            if not exec_res:
                continue
            try:
                # Get ads client for audit verification
                from app.models.integration_google_ads import IntegrationGoogleAds
                from app.integrations.google_ads.client import GoogleAdsClient
                ig_result = await self.db.execute(
                    select(IntegrationGoogleAds).where(
                        IntegrationGoogleAds.tenant_id == tenant_id,
                        IntegrationGoogleAds.is_active == True,
                    )
                )
                integration = ig_result.scalars().first()
                if integration:
                    ads_client = GoogleAdsClient(
                        customer_id=integration.customer_id,
                        refresh_token_encrypted=integration.refresh_token_encrypted,
                    )
                    audit_agent = PostExecutionAuditAgent(self.db, ads_client, tenant_id)
                    spec = action.action_payload or {}
                    deploy_res = exec_res.get("details", {})
                    pipeline_meta = spec.get("_pipeline_metadata", {})
                    if await audit_agent.should_audit(spec, deploy_res, pipeline_meta):
                        audit_result = await audit_agent.run_audit(
                            spec=spec,
                            deploy_result=deploy_res,
                            conversation_id=conversation_id,
                        )
            except Exception as e:
                logger.error("Unified post-execution audit failed", error=str(e))

        response: Dict[str, Any] = {
            "status": "completed",
            "succeeded": succeeded,
            "failed": failed,
            "results": execution_results,
        }
        if audit_result:
            response["audit"] = audit_result
        return response

    async def reject_actions(
        self,
        conversation_id: str,
        tenant_id: str,
        action_ids: List[str],
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
