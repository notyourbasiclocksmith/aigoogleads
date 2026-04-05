"""
Action Router — dispatches approved actions to the correct system's execution service.

Routes based on the `system` field on each proposed action.
Validates tenant ownership and account context before execution.
Returns normalized UnifiedExecutionResult for every action.
"""
from typing import Dict, Any, List
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class ActionRouter:
    """Routes approved actions to the correct mutation/execution service."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def execute(self, system: str, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single action and return normalized result.

        Returns:
            {
                "status": "success" | "failed" | "partial_success",
                "summary": str,
                "details": dict,
                "before": dict | None,
                "after": dict | None,
                "error": str | None,
            }
        """
        try:
            if system == "google_ads":
                return await self._execute_google_ads(action_type, payload)
            elif system == "meta_ads":
                return await self._execute_meta_ads(action_type, payload)
            elif system == "gbp":
                return await self._execute_gbp(action_type, payload)
            elif system == "image":
                return await self._execute_image(action_type, payload)
            else:
                return {"status": "failed", "error": f"Unknown system: {system}", "summary": ""}
        except Exception as e:
            logger.error("action_router_error", system=system, action=action_type, error=str(e))
            return {"status": "failed", "error": str(e)[:500], "summary": "Execution failed"}

    # ── Google Ads ─────────────────────────────────────────────

    async def _execute_google_ads(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route to Google Ads mutation service."""
        from app.models.integration_google_ads import IntegrationGoogleAds
        from app.integrations.google_ads.client import GoogleAdsClient
        from app.services.operator.mutation_service import GoogleAdsMutationService
        from sqlalchemy import select

        customer_id = payload.get("customer_id")
        if not customer_id:
            # Try to find the active integration
            result = await self.db.execute(
                select(IntegrationGoogleAds).where(
                    IntegrationGoogleAds.tenant_id == self.tenant_id,
                    IntegrationGoogleAds.is_active == True,
                )
            )
            integration = result.scalars().first()
            if not integration:
                return {"status": "failed", "error": "No active Google Ads integration", "summary": ""}
            customer_id = integration.customer_id
        else:
            from sqlalchemy import and_
            result = await self.db.execute(
                select(IntegrationGoogleAds).where(
                    and_(
                        IntegrationGoogleAds.tenant_id == self.tenant_id,
                        IntegrationGoogleAds.customer_id == customer_id,
                        IntegrationGoogleAds.is_active == True,
                    )
                )
            )
            integration = result.scalars().first()
            if not integration:
                return {"status": "failed", "error": f"No integration for customer {customer_id}", "summary": ""}

        ads_client = GoogleAdsClient(
            customer_id=customer_id,
            refresh_token_encrypted=integration.refresh_token_encrypted,
        )
        # Get business context for image generation actions
        biz_ctx = {}
        if action_type in ("generate_ad_image", "list_google_ads_assets"):
            from app.models.business_profile import BusinessProfile
            from app.models.tenant import Tenant
            try:
                tenant = await self.db.get(Tenant, str(self.tenant_id))
                bp_result = await self.db.execute(
                    select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
                )
                profile = bp_result.scalar_one_or_none()
                biz_ctx = {
                    "business_name": tenant.name if tenant else "",
                    "business_type": profile.industry_classification if profile else "service",
                }
            except Exception:
                pass
        mutation_svc = GoogleAdsMutationService(ads_client, business_context=biz_ctx)
        result = await mutation_svc.execute_action(action_type, payload)

        status = result.get("status", "failed")
        return {
            "status": status,
            "summary": f"Google Ads: {action_type} {'succeeded' if status == 'success' else 'failed'}",
            "details": result,
            "before": result.get("before"),
            "after": result.get("after"),
            "error": result.get("error"),
        }

    # ── Meta Ads ───────────────────────────────────────────────

    async def _execute_meta_ads(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route to Meta Ads mutation service."""
        from app.models.v2.integration_meta import IntegrationMeta
        from app.integrations.meta_ads.client import MetaAdsClient
        from app.services.meta_operator.mutation_service import MetaAdsMutationService
        from sqlalchemy import select

        result = await self.db.execute(
            select(IntegrationMeta).where(IntegrationMeta.tenant_id == self.tenant_id)
        )
        integration = result.scalars().first()
        if not integration:
            return {"status": "failed", "error": "No Meta Ads integration", "summary": ""}

        meta_client = MetaAdsClient(
            ad_account_id=integration.ad_account_id,
            access_token_encrypted=integration.access_token_encrypted,
        )
        mutation_svc = MetaAdsMutationService(meta_client)

        # Normalize action type (remove meta_ prefix for the mutation service)
        clean_type = action_type
        if clean_type.startswith("meta_"):
            # Map: pause_meta_campaign → pause_campaign, etc.
            clean_type = clean_type.replace("pause_meta_", "pause_").replace("enable_meta_", "enable_").replace("update_meta_", "update_")
        if clean_type == "generate_meta_creative":
            clean_type = "create_campaign"  # placeholder — creative gen is separate

        exec_result = await mutation_svc.execute_action(clean_type, payload)
        status = exec_result.get("status", "failed")
        return {
            "status": status,
            "summary": f"Meta Ads: {action_type} {'succeeded' if status == 'success' else 'failed'}",
            "details": exec_result,
            "error": exec_result.get("error"),
        }

    # ── GBP ────────────────────────────────────────────────────

    async def _execute_gbp(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route to GBP service."""
        from app.services.gbp_service import GBPService

        svc = GBPService(self.db)

        if action_type == "reply_review":
            result = await svc.reply_to_review(
                self.tenant_id,
                payload["review_id"],
                payload["reply_text"],
            )
            return {
                "status": "success" if result.get("status") != "error" else "failed",
                "summary": f"Replied to review {payload['review_id']}",
                "details": result,
                "error": result.get("error"),
            }

        elif action_type == "generate_review_reply":
            result = await svc.ai_reply_to_review(
                self.tenant_id,
                payload["review_id"],
                reviewer_name=payload.get("reviewer_name", ""),
                star_rating=payload.get("star_rating", 5),
                comment=payload.get("comment", ""),
                business_name=payload.get("business_name", ""),
                tone=payload.get("tone", "professional"),
            )
            return {
                "status": "success" if "ai_generated_reply" in result else "failed",
                "summary": f"AI replied to review",
                "details": result,
                "error": result.get("error"),
            }

        elif action_type == "reply_reviews_batch":
            reviews = payload.get("reviews", [])
            results = []
            succeeded = 0
            for r in reviews:
                try:
                    res = await svc.ai_reply_to_review(
                        self.tenant_id, r["review_id"],
                        reviewer_name=r.get("reviewer_name", ""),
                        star_rating=r.get("star_rating", 5),
                        comment=r.get("comment", ""),
                        tone=r.get("tone", "professional"),
                    )
                    results.append(res)
                    if "ai_generated_reply" in res:
                        succeeded += 1
                except Exception as e:
                    results.append({"error": str(e)[:200]})
            total = len(reviews)
            return {
                "status": "success" if succeeded == total else ("partial_success" if succeeded > 0 else "failed"),
                "summary": f"Replied to {succeeded}/{total} reviews",
                "details": {"succeeded_count": succeeded, "failed_count": total - succeeded, "results": results},
            }

        elif action_type in ("create_gbp_post", "generate_gbp_post"):
            if action_type == "generate_gbp_post":
                result = await svc.ai_create_post(
                    self.tenant_id,
                    topic=payload.get("topic", ""),
                    business_name=payload.get("business_name", ""),
                    business_type=payload.get("business_type", ""),
                    include_image=payload.get("include_image", False),
                )
            else:
                result = await svc.create_post(
                    self.tenant_id,
                    summary=payload.get("summary", ""),
                    topic_type=payload.get("topic_type", "STANDARD"),
                )
            return {
                "status": "success" if result.get("status") != "error" else "failed",
                "summary": f"GBP post created",
                "details": result,
                "error": result.get("error"),
            }

        return {"status": "failed", "error": f"Unknown GBP action: {action_type}", "summary": ""}

    # ── Image ──────────────────────────────────────────────────

    async def _execute_image(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route to image generation service."""
        from app.integrations.image_generator.client import ImageGeneratorClient

        client = ImageGeneratorClient()
        if not client.is_configured:
            return {"status": "failed", "error": "Image generator not configured", "summary": ""}

        if action_type == "generate_ad_image":
            result = await client.generate_ad_image(
                service=payload.get("service", ""),
                business_name=payload.get("business_name", ""),
                business_type=payload.get("business_type", ""),
                engine=payload.get("engine", "dalle"),
                style=payload.get("style", "photorealistic"),
                size=payload.get("size", "1024x1024"),
            )
        elif action_type == "generate_social_image":
            size_map = {"instagram": "1080x1080", "facebook": "1200x630", "google": "1024x1024"}
            platform = payload.get("platform", "instagram")
            prompt = f"Professional social media image for {platform}. Topic: {payload.get('topic', '')}."
            if payload.get("business_name"):
                prompt += f" Business: {payload['business_name']}."
            prompt += " Clean, modern, eye-catching, no text overlay."
            result = await client.generate_single(
                prompt=prompt,
                engine=payload.get("engine", "dalle"),
                style="photorealistic",
                size=size_map.get(platform, "1024x1024"),
            )
        else:
            result = await client.generate_single(
                prompt=payload.get("prompt", ""),
                engine=payload.get("engine", "dalle"),
                style=payload.get("style", "photorealistic"),
                size=payload.get("size", "1024x1024"),
            )

        success = result.get("success", False)
        return {
            "status": "success" if success else "failed",
            "summary": f"Image {'generated' if success else 'generation failed'}",
            "details": result,
            "error": result.get("error"),
        }
