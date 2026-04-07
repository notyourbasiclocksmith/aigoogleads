"""
Google Ads Operator Service — orchestrates the full read → analyze → propose → execute flow.

This is the main service that the API endpoints call.
"""
import uuid
import time
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
from app.services.operator.post_execution_audit import PostExecutionAuditAgent
from app.services.operator.landing_page_agent import LandingPageAgent

logger = structlog.get_logger()

# Simple TTL cache for account context (avoid re-fetching on every message)
_context_cache: dict[str, tuple[float, dict]] = {}
CONTEXT_CACHE_TTL = 300  # 5 minutes

# Landing page action types that the operator can recommend and auto-execute
LANDING_PAGE_ACTIONS = {
    "edit_landing_page",
    "regenerate_landing_page",
    "approve_landing_page",
    "generate_landing_page_images",
    "list_landing_pages",
}


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
            # Extract campaign type and other hints from Claude's original intent
            intent_payload = claude_intent.get("payload", {})
            intent_hints = {
                "campaign_type": intent_payload.get("campaign", {}).get("campaign_type"),
                "services": intent_payload.get("services"),
                "locations": intent_payload.get("locations"),
                "forward_phone": intent_payload.get("forward_phone"),
            }
            spec = await pipeline.run(
                user_prompt=user_message,
                account_context=account_context,
                conversation_id=conversation_id,
                intent_hints=intent_hints,
            )
            return spec
        except Exception as e:
            logger.error("Campaign pipeline failed", error=str(e))
            # Fall back to Claude's original thin spec
            return claude_intent.get("payload", {})

    # ── LANDING PAGE ACTION DETECTION & EXECUTION ────────────────

    def _has_landing_page_actions(self, claude_response: Dict[str, Any]) -> bool:
        """Check if Claude recommended any landing page actions."""
        for action in claude_response.get("recommended_actions", []):
            if action.get("action_type") in LANDING_PAGE_ACTIONS:
                return True
        return False

    async def _execute_landing_page_actions(
        self,
        conversation_id: str,
        tenant_id: str,
        claude_response: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Auto-execute landing page actions from Claude's response.
        These are safe, non-destructive operations that don't modify the ad account.
        Returns list of execution results.
        """
        agent = LandingPageAgent(self.db, tenant_id)
        results = []

        for action in claude_response.get("recommended_actions", []):
            action_type = action.get("action_type")
            payload = action.get("action_payload", {})

            if action_type not in LANDING_PAGE_ACTIONS:
                continue

            try:
                if action_type == "edit_landing_page":
                    result = await agent.edit_variant(
                        landing_page_id=payload.get("landing_page_id", ""),
                        variant_key=payload.get("variant_key", "A"),
                        edit_prompt=payload.get("edit_prompt", ""),
                        conversation_id=payload.get("conversation_id", conversation_id),
                    )
                    action["_execution_result"] = result
                    action["_auto_executed"] = True
                    results.append({
                        "action_type": action_type,
                        "status": "error" if result.get("error") else "success",
                        "result": result,
                    })

                elif action_type == "regenerate_landing_page":
                    result = await agent.regenerate_variant(
                        landing_page_id=payload.get("landing_page_id", ""),
                        variant_key=payload.get("variant_key", "A"),
                        new_angle=payload.get("new_angle", ""),
                        conversation_id=payload.get("conversation_id", conversation_id),
                    )
                    action["_execution_result"] = result
                    action["_auto_executed"] = True
                    results.append({
                        "action_type": action_type,
                        "status": "error" if result.get("error") else "success",
                        "result": result,
                    })

                elif action_type == "approve_landing_page":
                    result = await agent.approve_variant(
                        landing_page_id=payload.get("landing_page_id", ""),
                        variant_key=payload.get("variant_key", "A"),
                        campaign_spec={},  # No campaign spec when approving standalone
                    )
                    action["_execution_result"] = result
                    action["_auto_executed"] = True
                    results.append({
                        "action_type": action_type,
                        "status": "error" if result.get("error") else "success",
                        "result": result,
                    })

                elif action_type == "generate_landing_page_images":
                    result = await agent.generate_images(
                        landing_page_id=payload.get("landing_page_id", ""),
                        conversation_id=conversation_id,
                    )
                    action["_execution_result"] = result
                    action["_auto_executed"] = True
                    results.append({
                        "action_type": action_type,
                        "status": "error" if result.get("error") else "success",
                        "result": result,
                    })

                elif action_type == "list_landing_pages":
                    result = await self._list_landing_pages(
                        tenant_id=tenant_id,
                        service_filter=payload.get("service_filter"),
                    )
                    action["_execution_result"] = result
                    action["_auto_executed"] = True
                    results.append({
                        "action_type": action_type,
                        "status": "success",
                        "result": result,
                    })

            except Exception as e:
                logger.error("Landing page action failed",
                    action_type=action_type, error=str(e))
                results.append({
                    "action_type": action_type,
                    "status": "error",
                    "error": str(e)[:200],
                })

        return results

    async def _list_landing_pages(
        self, tenant_id: str, service_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List landing pages for the tenant."""
        from app.models.landing_page import LandingPage

        query = select(LandingPage).where(
            LandingPage.tenant_id == tenant_id,
        ).order_by(LandingPage.created_at.desc()).limit(20)

        if service_filter:
            query = query.where(LandingPage.service.ilike(f"%{service_filter}%"))

        result = await self.db.execute(query)
        pages = result.scalars().all()

        return {
            "pages": [
                {
                    "landing_page_id": p.id,
                    "name": p.name,
                    "service": p.service,
                    "status": p.status,
                    "url": p.url or f"/lp/{p.slug}",
                    "audit_score": p.audit_score,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "variant_count": len(p.variants) if p.variants else 0,
                }
                for p in pages
            ],
            "total": len(pages),
        }

    async def _execute_single_lp_action(
        self,
        tenant_id: str,
        conversation_id: str,
        action_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single landing page action via the LandingPageAgent."""
        agent = LandingPageAgent(self.db, tenant_id)

        if action_type == "edit_landing_page":
            result = await agent.edit_variant(
                landing_page_id=payload.get("landing_page_id", ""),
                variant_key=payload.get("variant_key", "A"),
                edit_prompt=payload.get("edit_prompt", ""),
                conversation_id=payload.get("conversation_id", conversation_id),
            )
        elif action_type == "regenerate_landing_page":
            result = await agent.regenerate_variant(
                landing_page_id=payload.get("landing_page_id", ""),
                variant_key=payload.get("variant_key", "A"),
                new_angle=payload.get("new_angle", ""),
                conversation_id=payload.get("conversation_id", conversation_id),
            )
        elif action_type == "approve_landing_page":
            result = await agent.approve_variant(
                landing_page_id=payload.get("landing_page_id", ""),
                variant_key=payload.get("variant_key", "A"),
                campaign_spec={},
            )
        elif action_type == "generate_landing_page_images":
            result = await agent.generate_images(
                landing_page_id=payload.get("landing_page_id", ""),
                conversation_id=conversation_id,
            )
        elif action_type == "list_landing_pages":
            result = await self._list_landing_pages(
                tenant_id=tenant_id,
                service_filter=payload.get("service_filter"),
            )
        else:
            return {"status": "failed", "error": f"Unknown landing page action: {action_type}"}

        if result.get("error"):
            return {"status": "failed", "error": result["error"]}
        result["status"] = "success"
        return result

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
        image_engine: Optional[str] = None,
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

        # Use cached context if available (avoid full diagnosis on every message)
        cache_key = f"{customer_id}:{date_range}"
        now = time.time()
        cached = _context_cache.get(cache_key)
        if cached and (now - cached[0]) < CONTEXT_CACHE_TTL:
            account_context = cached[1]
            logger.info("Using cached account context", customer_id=customer_id, age_seconds=int(now - cached[0]))
        else:
            account_context = await context_svc.build_full_context(date_range)
            _context_cache[cache_key] = (now, account_context)
            logger.info("Built and cached account context", customer_id=customer_id)

        # Inject landing page data so Claude can reference existing pages
        try:
            lp_data = await self._list_landing_pages(tenant_id)
            account_context["landing_pages"] = lp_data.get("pages", [])
        except Exception:
            account_context["landing_pages"] = []

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

        # ── PROMPT ENHANCEMENT: Clean up messy user input before Claude ──
        enhanced_data = {}
        effective_message = message
        try:
            from app.services.operator.prompt_enhancer import enhance_prompt
            biz_ctx = {}
            from app.models.business_profile import BusinessProfile
            bp_result = await self.db.execute(
                select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
            )
            bp = bp_result.scalar_one_or_none()
            if bp:
                biz_ctx = {
                    "name": getattr(bp, "description", "") or "",
                    "industry": bp.industry_classification or "",
                    "services": bp.services_json or [],
                    "city": bp.city or "",
                    "state": bp.state or "",
                }
            enhanced_data = await enhance_prompt(
                raw_prompt=message,
                business_context=biz_ctx,
                existing_campaigns=account_context.get("campaigns", []),
            )
            if enhanced_data.get("enhanced_prompt") and not enhanced_data.get("skipped"):
                effective_message = enhanced_data["enhanced_prompt"]
                logger.info("Prompt enhanced", original_len=len(message), enhanced_len=len(effective_message))
                # Save enhancement as a progress message
                enhance_msg = OperatorMessage(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    role="assistant",
                    content=effective_message,
                    structured_payload={
                        "type": "prompt_enhanced",
                        "original": message,
                        "enhanced": effective_message,
                        "campaign_brief": enhanced_data.get("campaign_brief"),
                        "ad_group_briefs": enhanced_data.get("ad_group_briefs"),
                        "image_prompts": enhanced_data.get("image_prompts"),
                        "suggested_negatives": enhanced_data.get("suggested_negatives"),
                    },
                )
                self.db.add(enhance_msg)
                await self.db.flush()
        except Exception as e:
            logger.warning("Prompt enhancement failed, using original", error=str(e))

        # Call Claude with enhanced prompt
        claude_response = await self.claude.analyze(
            user_message=effective_message,
            account_context=account_context,
            conversation_history=conversation_history[:-1],  # Exclude the message we just added
        )

        # ── PIPELINE INTERCEPT: If Claude recommends deploy_full_campaign,
        # run the multi-agent pipeline to produce an expert-quality spec ──
        if self._should_use_pipeline(claude_response):
            logger.info("Pipeline intercept triggered", conversation_id=conversation_id)
            intent = self._extract_campaign_intent(claude_response, effective_message)
            pipeline_spec = await self._run_campaign_pipeline(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                customer_id=customer_id,
                user_message=effective_message,
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

                    # Attach image prompts from enhancer for post-deploy generation
                    if enhanced_data.get("image_prompts"):
                        pipeline_spec["_image_prompts"] = enhanced_data["image_prompts"]

        # ── LANDING PAGE ACTION INTERCEPT: Auto-execute landing page actions
        # since they are non-destructive (don't modify ad account) ──
        lp_results = []
        if self._has_landing_page_actions(claude_response):
            logger.info("Landing page action detected", conversation_id=conversation_id)
            lp_results = await self._execute_landing_page_actions(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                claude_response=claude_response,
            )
            # Enrich Claude's response with execution results
            if lp_results:
                claude_response["_landing_page_results"] = lp_results
                # Update summary to include LP action outcomes
                lp_successes = [r for r in lp_results if r.get("status") == "success"]
                lp_errors = [r for r in lp_results if r.get("status") == "error"]
                if lp_successes:
                    lp_summary_parts = []
                    for r in lp_successes:
                        res = r.get("result", {})
                        if r["action_type"] == "edit_landing_page":
                            lp_summary_parts.append(
                                f"Edited variant {res.get('variant_key', '?')}: \"{res.get('edit_applied', '')}\""
                            )
                        elif r["action_type"] == "regenerate_landing_page":
                            lp_summary_parts.append(
                                f"Regenerated variant {res.get('variant_key', '?')} with {res.get('angle', 'fresh')} angle"
                            )
                        elif r["action_type"] == "approve_landing_page":
                            lp_summary_parts.append(
                                f"Approved variant {res.get('variant_approved', '?')} — published at {res.get('url', '')}"
                            )
                        elif r["action_type"] == "generate_landing_page_images":
                            imgs = res.get("images", [])
                            ok = sum(1 for i in imgs if i.get("status") == "success")
                            lp_summary_parts.append(f"Generated {ok}/{len(imgs)} hero images")
                        elif r["action_type"] == "list_landing_pages":
                            pages = res.get("pages", [])
                            lp_summary_parts.append(f"Found {len(pages)} landing page(s)")
                    if lp_summary_parts:
                        extra_summary = " | ".join(lp_summary_parts)
                        claude_response["summary"] = (
                            claude_response.get("summary", "") + f" [{extra_summary}]"
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

        # Save proposed actions (skip auto-executed landing page actions)
        proposed_actions = []
        for action in claude_response.get("recommended_actions", []):
            # Landing page actions that were auto-executed get saved as "executed"
            is_auto_executed = action.get("_auto_executed", False)
            status = "executed" if is_auto_executed else "proposed"

            # Inject user's preferred image engine into image actions
            action_payload = action.get("action_payload", {})
            if image_engine and action["action_type"] == "generate_ad_image":
                action_payload["engine"] = image_engine

            pa = ProposedAction(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                message_id=assistant_msg.id,
                action_type=action["action_type"],
                label=action.get("label", action["action_type"]),
                reasoning=action.get("reasoning"),
                expected_impact=action.get("expected_impact"),
                risk_level=action.get("risk_level", "low" if is_auto_executed else "medium"),
                action_payload=action_payload,
                status=status,
            )
            if is_auto_executed:
                pa.executed_at = datetime.now(timezone.utc)
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
                "_execution_result": action.get("_execution_result") if is_auto_executed else None,
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
            "landing_page_results": lp_results if lp_results else None,
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

            # Execute — route landing page actions to LandingPageAgent
            try:
                if action.action_type in LANDING_PAGE_ACTIONS:
                    exec_result = await self._execute_single_lp_action(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        action_type=action.action_type,
                        payload=action.action_payload or {},
                    )
                else:
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

        # ── POST-EXECUTION AUDIT for deploy_full_campaign ──
        audit_result = None
        for action in actions:
            if action.action_type != "deploy_full_campaign":
                continue
            exec_res = next(
                (r for r in execution_results
                 if r["action_id"] == action.id and r["status"] in ("success", "partial")),
                None,
            )
            if not exec_res:
                continue

            try:
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
                    logger.info("Post-execution audit complete",
                        status=audit_result.get("status"),
                        score=audit_result.get("score"),
                        issues=len(audit_result.get("issues", [])),
                        fixes=len(audit_result.get("fix_actions", [])),
                    )
            except Exception as e:
                logger.error("Post-execution audit failed", error=str(e))

            # ── AUTO-GENERATE IMAGES after successful campaign deploy ──
            image_prompts = spec.get("_image_prompts", [])
            campaign_id = deploy_res.get("campaign", {}).get("campaign_id")
            if image_prompts and campaign_id and exec_res.get("status") in ("success", "partial"):
                img_results = []
                for ip in image_prompts:
                    try:
                        img_result = await mutation_svc.execute_action(
                            "generate_ad_image",
                            {
                                "prompt": ip.get("prompt", ""),
                                "engine": ip.get("engine", "google"),
                                "style": ip.get("style", "photorealistic"),
                                "size": "1200x628",  # Google Ads landscape
                                "upload_to_google": True,
                                "campaign_id": campaign_id,
                                "asset_name": f"{ip.get('service', 'Ad')} - Campaign Image",
                            },
                        )
                        img_results.append({
                            "service": ip.get("service"),
                            "status": img_result.get("status"),
                            "image_url": img_result.get("image_url"),
                        })
                    except Exception as img_err:
                        logger.warning("Image generation failed for service",
                            service=ip.get("service"), error=str(img_err)[:200])
                        img_results.append({
                            "service": ip.get("service"),
                            "status": "failed",
                            "error": str(img_err)[:100],
                        })

                if img_results:
                    img_msg = OperatorMessage(
                        id=str(uuid.uuid4()),
                        conversation_id=conversation_id,
                        role="assistant",
                        content=f"Generated {sum(1 for r in img_results if r.get('status') == 'success')} images for your campaign.",
                        structured_payload={
                            "type": "image_generation_result",
                            "images": img_results,
                            "campaign_id": campaign_id,
                        },
                    )
                    self.db.add(img_msg)
                    await self.db.flush()
                    logger.info("Auto-generated campaign images",
                        total=len(img_results),
                        success=sum(1 for r in img_results if r.get("status") == "success"),
                    )

        # Invalidate context cache after mutations
        for key in list(_context_cache.keys()):
            if key.startswith(customer_id):
                del _context_cache[key]

        response = {
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
