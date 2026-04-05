"""
Google Ads Operator Service — orchestrates the full read → analyze → propose → execute flow.

This is the main service that the API endpoints call.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.operator import OperatorConversation, OperatorMessage, ProposedAction, ActionExecutionLog
from app.models.integration_google_ads import IntegrationGoogleAds
from app.integrations.google_ads.client import GoogleAdsClient
from app.services.operator.context_service import GoogleAdsContextService
from app.services.operator.mutation_service import GoogleAdsMutationService
from app.services.operator.claude_agent_service import ClaudeAdsAgentService
from app.services.operator.campaign_agent_pipeline import CampaignAgentPipeline

logger = structlog.get_logger()


class GoogleAdsOperatorService:
    """Orchestrates the Claude Operator chat flow."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.claude = ClaudeAdsAgentService()

    async def _get_ads_client(self, tenant_id: str, customer_id: str) -> GoogleAdsClient:
        """Get an authenticated Google Ads client for a tenant's account."""
        result = await self.db.execute(
            select(IntegrationGoogleAds).where(
                and_(
                    IntegrationGoogleAds.tenant_id == tenant_id,
                    IntegrationGoogleAds.customer_id == customer_id,
                    IntegrationGoogleAds.is_active == True,
                )
            )
        )
        integration = result.scalars().first()
        if not integration:
            raise ValueError(f"No active Google Ads integration found for customer {customer_id}")
        return GoogleAdsClient(
            customer_id=customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
        )

    async def _get_business_context(self, tenant_id: str) -> Dict[str, Any]:
        """Get business name/type for image generation metadata."""
        from app.models.business_profile import BusinessProfile
        from app.models.tenant import Tenant
        try:
            tenant = await self.db.get(Tenant, tenant_id)
            bp_result = await self.db.execute(
                select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
            )
            profile = bp_result.scalar_one_or_none()
            return {
                "business_name": tenant.name if tenant else "",
                "business_type": profile.industry_classification if profile else "service",
            }
        except Exception:
            return {}

    # ── CAMPAIGN PIPELINE DETECTION ─────────────────────────────

    def _should_use_pipeline(self, claude_response: Dict[str, Any]) -> bool:
        """Check if Claude recommended a deploy_full_campaign that should trigger the multi-agent pipeline."""
        for action in claude_response.get("recommended_actions", []):
            if action.get("action_type") == "deploy_full_campaign":
                return True
        return False

    def _extract_campaign_intent(self, claude_response: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """Extract the campaign creation intent from Claude's thin response."""
        for action in claude_response.get("recommended_actions", []):
            if action.get("action_type") == "deploy_full_campaign":
                return {
                    "payload": action.get("action_payload", {}),
                    "label": action.get("label", ""),
                    "reasoning": action.get("reasoning", ""),
                    "user_message": user_message,
                }
        return {"user_message": user_message}

    async def _run_campaign_pipeline(
        self,
        conversation_id: str,
        tenant_id: str,
        customer_id: str,
        user_message: str,
        account_context: Dict[str, Any],
        claude_intent: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run the multi-agent pipeline and return the enriched deploy_full_campaign payload."""
        pipeline = CampaignAgentPipeline(self.db, tenant_id, customer_id)
        try:
            spec = await pipeline.run(
                user_prompt=user_message,
                account_context=account_context,
                conversation_id=conversation_id,
            )
            return spec
        except Exception as e:
            logger.error("Campaign pipeline failed", error=str(e))
            # Fall back to Claude's original thin spec
            return claude_intent.get("payload", {})

    # ── CONVERSATION MANAGEMENT ──────────────────────────────────

    async def create_conversation(self, tenant_id: str, customer_id: str, user_id: str) -> Dict[str, Any]:
        """Create a new operator conversation."""
        conv = OperatorConversation(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            customer_id=customer_id,
            created_by=user_id,
            title="New conversation",
            mode="google_ads",
        )
        self.db.add(conv)
        await self.db.flush()
        return {"conversation_id": conv.id, "title": conv.title, "created_at": conv.created_at.isoformat()}

    async def list_conversations(self, tenant_id: str, customer_id: str) -> List[Dict[str, Any]]:
        """List conversations for a tenant/account."""
        result = await self.db.execute(
            select(OperatorConversation)
            .where(
                and_(
                    OperatorConversation.tenant_id == tenant_id,
                    OperatorConversation.customer_id == customer_id,
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

    async def get_conversation(self, conversation_id: str, tenant_id: str) -> Dict[str, Any]:
        """Get full conversation with messages."""
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

        # Get messages
        msg_result = await self.db.execute(
            select(OperatorMessage)
            .where(OperatorMessage.conversation_id == conversation_id)
            .order_by(OperatorMessage.created_at)
        )
        messages = msg_result.scalars().all()

        # Get proposed actions for each assistant message
        action_result = await self.db.execute(
            select(ProposedAction)
            .where(ProposedAction.conversation_id == conversation_id)
            .order_by(ProposedAction.created_at)
        )
        actions = action_result.scalars().all()
        actions_by_msg = {}
        for a in actions:
            actions_by_msg.setdefault(a.message_id, []).append({
                "id": a.id,
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
            "customer_id": conv.customer_id,
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
        customer_id: str,
        user_id: str,
        message: str,
        date_range: str = "LAST_30_DAYS",
    ) -> Dict[str, Any]:
        """Process a user chat message: read account → analyze with Claude → store results."""

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

        # Update conversation title if first message
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

        # Get Google Ads client
        ads_client = await self._get_ads_client(tenant_id, customer_id)
        context_svc = GoogleAdsContextService(ads_client)

        # Build account context
        account_context = await context_svc.build_full_context(date_range)

        # Get conversation history for Claude
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
            conversation_history=conversation_history[:-1],  # Exclude the message we just added
        )

        # ── PIPELINE INTERCEPT: If Claude recommends deploy_full_campaign,
        # run the multi-agent pipeline to produce an expert-quality spec ──
        if self._should_use_pipeline(claude_response):
            logger.info("Pipeline intercept triggered", conversation_id=conversation_id)
            intent = self._extract_campaign_intent(claude_response, message)
            pipeline_spec = await self._run_campaign_pipeline(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                customer_id=customer_id,
                user_message=message,
                account_context=account_context,
                claude_intent=intent,
            )
            # Replace the thin Claude payload with the pipeline-generated spec
            for action in claude_response.get("recommended_actions", []):
                if action.get("action_type") == "deploy_full_campaign":
                    action["action_payload"] = pipeline_spec
                    action["label"] = f"Deploy Campaign: {pipeline_spec.get('campaign', {}).get('name', 'AI Campaign')}"
                    # Enrich reasoning with pipeline metadata
                    meta = pipeline_spec.get("_pipeline_metadata", {})
                    qa_score = meta.get("qa_score")
                    if qa_score:
                        action["reasoning"] = (
                            f"{action.get('reasoning', '')} "
                            f"[Pipeline QA Score: {qa_score}/100]"
                        ).strip()

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

    # ── APPROVE / REJECT / EXECUTE ──────────────────────────────

    async def approve_actions(
        self,
        conversation_id: str,
        tenant_id: str,
        customer_id: str,
        user_id: str,
        action_ids: List[str],
    ) -> Dict[str, Any]:
        """Approve and execute proposed actions."""

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

        # Get actions
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

        # Get ads client + business context for image generation
        ads_client = await self._get_ads_client(tenant_id, customer_id)
        biz_ctx = await self._get_business_context(tenant_id)
        mutation_svc = GoogleAdsMutationService(ads_client, business_context=biz_ctx)

        execution_results = []
        now = datetime.now(timezone.utc)

        for action in actions:
            action.status = "approved"
            action.approved_at = now
            action.executed_by = user_id

            # Execute
            try:
                exec_result = await mutation_svc.execute_action(
                    action.action_type, action.action_payload
                )

                exec_status = exec_result.get("status", "failed")
                action.status = "executed" if exec_status == "success" else "failed"
                action.executed_at = datetime.now(timezone.utc)

                # Log execution
                log = ActionExecutionLog(
                    id=str(uuid.uuid4()),
                    proposed_action_id=action.id,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
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
                    customer_id=customer_id,
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

        # Save execution result as a system message in the conversation
        succeeded = sum(1 for r in execution_results if r["status"] == "success")
        failed = sum(1 for r in execution_results if r["status"] != "success")

        exec_msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=f"Executed {succeeded} action(s) successfully. {failed} failed." if failed else f"All {succeeded} action(s) executed successfully.",
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

        return {
            "status": "completed",
            "succeeded": succeeded,
            "failed": failed,
            "results": execution_results,
        }

    async def reject_actions(
        self,
        conversation_id: str,
        tenant_id: str,
        action_ids: List[str],
    ) -> Dict[str, Any]:
        """Reject proposed actions."""
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
