"""
Meta Ads Mutation Service — safe write operations with before/after state capture.

Handles the full range of Meta ad creation/modification operations:
- Campaign CRUD
- Ad Set CRUD with proper targeting
- Creative creation (single image, carousel)
- Image upload to Meta ad library
- Ad creation and linking
- Budget and status updates
"""
import json
from typing import Dict, Any
import structlog

from app.integrations.meta_ads.client import MetaAdsClient

logger = structlog.get_logger()


class MetaAdsMutationService:
    """Executes Meta Ads mutations with audit trail."""

    def __init__(self, client: MetaAdsClient):
        self.client = client

    async def execute_action(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route action to the appropriate handler."""
        handlers = {
            "pause_campaign": self._pause_campaign,
            "enable_campaign": self._enable_campaign,
            "update_campaign_budget": self._update_campaign_budget,
            "create_campaign": self._create_campaign,
            "create_adset": self._create_adset,
            "create_ad_creative": self._create_ad_creative,
            "create_carousel_creative": self._create_carousel_creative,
            "create_ad": self._create_ad,
            "upload_image": self._upload_image,
            "pause_adset": self._pause_adset,
            "enable_adset": self._enable_adset,
            "update_adset_budget": self._update_adset_budget,
            "pause_ad": self._pause_ad,
            "enable_ad": self._enable_ad,
            "deploy_full_meta_campaign": self._deploy_full_meta_campaign,
            "search_targeting": self._search_targeting,
            "preview_ad": self._preview_ad,
            "get_instagram_accounts": self._get_instagram_accounts,
        }
        handler = handlers.get(action_type)
        if not handler:
            return {"status": "failed", "error": f"Unknown action type: {action_type}"}
        try:
            return await handler(payload)
        except Exception as e:
            logger.error("Meta mutation failed", action=action_type, error=str(e))
            return {"status": "failed", "error": str(e)[:500]}

    # ── Campaign Operations ───────────────────────────────────

    async def _pause_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id = payload["campaign_id"]
        result = await self.client.update_campaign_status(campaign_id, "PAUSED")
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "campaign_id": campaign_id, "new_status": "PAUSED"}

    async def _enable_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id = payload["campaign_id"]
        result = await self.client.update_campaign_status(campaign_id, "ACTIVE")
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "campaign_id": campaign_id, "new_status": "ACTIVE"}

    async def _update_campaign_budget(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id = payload["campaign_id"]
        new_budget = payload.get("new_daily_budget_cents", payload.get("daily_budget", 2000))
        result = await self.client.update_campaign_budget(campaign_id, new_budget)
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "campaign_id": campaign_id, "new_daily_budget_cents": new_budget}

    async def _create_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("name", "New Campaign")
        objective = payload.get("objective", "OUTCOME_LEADS")
        daily_budget = payload.get("daily_budget_cents", 2000)
        special_ad_categories = payload.get("special_ad_categories", [])
        result = await self.client.create_campaign(
            name, objective, daily_budget, "PAUSED",
            special_ad_categories=special_ad_categories,
        )
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "campaign_id": result.get("id"), "name": name}

    # ── Ad Set Operations ─────────────────────────────────────

    async def _create_adset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        campaign_id = payload.get("campaign_id")
        if not campaign_id:
            return {"status": "failed", "error": "campaign_id is required"}
        name = payload.get("name", "New Ad Set")
        daily_budget = payload.get("daily_budget_cents", 2000)
        optimization_goal = payload.get("optimization_goal", "LEAD_GENERATION")
        billing_event = payload.get("billing_event", "IMPRESSIONS")
        targeting = payload.get("targeting")
        start_time = payload.get("start_time")
        promoted_object = payload.get("promoted_object")
        destination_type = payload.get("destination_type")
        bid_amount = payload.get("bid_amount")

        result = await self.client.create_adset(
            campaign_id=campaign_id, name=name, daily_budget=daily_budget,
            optimization_goal=optimization_goal, billing_event=billing_event,
            targeting=targeting, status="PAUSED", start_time=start_time,
            promoted_object=promoted_object, destination_type=destination_type,
            bid_amount=bid_amount,
        )
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "adset_id": result.get("id"), "name": name}

    async def _pause_adset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        adset_id = payload["adset_id"]
        result = await self.client._post(adset_id, {"status": "PAUSED"})
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "adset_id": adset_id, "new_status": "PAUSED"}

    async def _enable_adset(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        adset_id = payload["adset_id"]
        result = await self.client._post(adset_id, {"status": "ACTIVE"})
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "adset_id": adset_id, "new_status": "ACTIVE"}

    async def _update_adset_budget(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        adset_id = payload["adset_id"]
        new_budget = payload.get("new_daily_budget_cents", 2000)
        result = await self.client._post(adset_id, {"daily_budget": str(new_budget)})
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "adset_id": adset_id, "new_daily_budget_cents": new_budget}

    # ── Creative Operations ───────────────────────────────────

    async def _upload_image(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upload an image to Meta's ad library first (required before creating creatives)."""
        image_url = payload.get("image_url")
        if not image_url:
            return {"status": "failed", "error": "image_url is required"}
        name = payload.get("name", "Ad Image")
        result = await self.client.upload_ad_image(image_url, name)
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "image_hash": result.get("image_hash"), "name": name}

    async def _create_ad_creative(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        page_id = payload.get("page_id")
        if not page_id:
            return {"status": "failed", "error": "page_id is required — connect a Facebook Page first"}

        name = payload.get("name", "New Creative")
        message = payload.get("message", "")
        link = payload.get("link")
        image_url = payload.get("image_url")
        image_hash = payload.get("image_hash")
        headline = payload.get("headline")
        description = payload.get("description")
        cta = payload.get("call_to_action_type", "LEARN_MORE")
        instagram_user_id = payload.get("instagram_user_id")

        # If image_url provided but no image_hash, upload first
        if image_url and not image_hash:
            upload = await self.client.upload_ad_image(image_url, f"{name} - Image")
            if upload.get("image_hash"):
                image_hash = upload["image_hash"]
                logger.info("Auto-uploaded image to Meta", hash=image_hash)

        result = await self.client.create_ad_creative(
            name=name, page_id=page_id, message=message,
            link=link, image_url=image_url if not image_hash else None,
            image_hash=image_hash,
            call_to_action_type=cta,
            headline=headline, description=description,
            instagram_user_id=instagram_user_id,
        )
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "creative_id": result.get("id"), "name": name}

    async def _create_carousel_creative(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        page_id = payload.get("page_id")
        if not page_id:
            return {"status": "failed", "error": "page_id is required"}

        name = payload.get("name", "Carousel Creative")
        message = payload.get("message", "")
        link = payload.get("link", "")
        cards = payload.get("cards", [])
        cta = payload.get("call_to_action_type", "LEARN_MORE")
        instagram_user_id = payload.get("instagram_user_id")

        if len(cards) < 2:
            return {"status": "failed", "error": "Carousel requires at least 2 cards"}

        # Auto-upload card images if needed
        for card in cards:
            if card.get("image_url") and not card.get("image_hash"):
                upload = await self.client.upload_ad_image(
                    card["image_url"], f"Carousel - {card.get('name', 'Card')}"
                )
                if upload.get("image_hash"):
                    card["image_hash"] = upload["image_hash"]

        result = await self.client.create_carousel_creative(
            name=name, page_id=page_id, message=message,
            cards=cards, link=link, call_to_action_type=cta,
            instagram_user_id=instagram_user_id,
        )
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "creative_id": result.get("id"), "name": name}

    # ── Ad Operations ─────────────────────────────────────────

    async def _create_ad(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        adset_id = payload.get("adset_id")
        creative_id = payload.get("creative_id")
        if not adset_id or not creative_id:
            return {"status": "failed", "error": "adset_id and creative_id are required"}

        name = payload.get("name", "New Ad")
        result = await self.client.create_ad(adset_id, name, creative_id, "PAUSED")
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "ad_id": result.get("id"), "name": name}

    async def _pause_ad(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ad_id = payload["ad_id"]
        result = await self.client._post(ad_id, {"status": "PAUSED"})
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "ad_id": ad_id, "new_status": "PAUSED"}

    async def _enable_ad(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ad_id = payload["ad_id"]
        result = await self.client._post(ad_id, {"status": "ACTIVE"})
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "ad_id": ad_id, "new_status": "ACTIVE"}

    # ── Read-Only Operations (auto-executed, no confirmation) ──

    async def _search_targeting(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Search for Meta targeting options — interests, behaviors, demographics."""
        query = payload.get("query", "")
        target_type = payload.get("type", "adinterest")  # adinterest, adTargetingCategory, etc.
        if not query:
            return {"status": "failed", "error": "query is required"}
        results = await self.client.get_targeting_search(query, target_type)
        return {
            "status": "success",
            "query": query,
            "type": target_type,
            "results": [
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "audience_size_lower_bound": r.get("audience_size_lower_bound"),
                    "audience_size_upper_bound": r.get("audience_size_upper_bound"),
                    "path": r.get("path", []),
                    "description": r.get("description", ""),
                    "topic": r.get("topic", ""),
                }
                for r in results[:20]
            ],
            "count": len(results),
        }

    async def _preview_ad(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get HTML preview of an ad creative before publishing."""
        creative_id = payload.get("creative_id")
        if not creative_id:
            return {"status": "failed", "error": "creative_id is required"}
        ad_format = payload.get("ad_format", "DESKTOP_FEED_STANDARD")
        result = await self.client.get_ad_preview(creative_id, ad_format)
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        previews = result.get("data", [])
        return {
            "status": "success",
            "creative_id": creative_id,
            "format": ad_format,
            "preview_html": previews[0].get("body", "") if previews else "",
            "preview_count": len(previews),
        }

    async def _get_instagram_accounts(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """List Instagram accounts linked to this ad account."""
        accounts = await self.client.get_instagram_accounts()
        return {
            "status": "success",
            "instagram_accounts": accounts,
            "count": len(accounts),
        }

    # ── Full Campaign Deployment ──────────────────────────────

    async def _deploy_full_meta_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deploy a complete Meta campaign: Campaign → Ad Set → Creative → Ad.
        All created in PAUSED status for review.
        """
        results: Dict[str, Any] = {"status": "success", "steps": []}

        # 1. Create Campaign
        campaign_data = payload.get("campaign", {})
        campaign_result = await self._create_campaign({
            "name": campaign_data.get("name", "AI Campaign"),
            "objective": campaign_data.get("objective", "OUTCOME_LEADS"),
            "daily_budget_cents": campaign_data.get("daily_budget_cents", 2000),
            "special_ad_categories": campaign_data.get("special_ad_categories", []),
        })
        results["steps"].append({"step": "campaign", "result": campaign_result})
        if campaign_result.get("status") != "success":
            results["status"] = "failed"
            results["error"] = f"Campaign creation failed: {campaign_result.get('error')}"
            return results

        campaign_id = campaign_result["campaign_id"]
        results["campaign_id"] = campaign_id

        # 2. Create Ad Sets
        adsets = payload.get("adsets", [payload.get("adset", {})])
        for adset_data in adsets:
            if not adset_data:
                continue
            adset_data["campaign_id"] = campaign_id
            adset_result = await self._create_adset(adset_data)
            results["steps"].append({"step": "adset", "result": adset_result})
            if adset_result.get("status") != "success":
                results["status"] = "partial"
                continue

            adset_id = adset_result["adset_id"]

            # 3. Create Creatives & Ads for this adset
            creatives = adset_data.get("creatives", adset_data.get("ads", []))
            for creative_data in creatives:
                if not creative_data:
                    continue
                # Create creative
                creative_data.setdefault("page_id", payload.get("page_id"))
                if creative_data.get("cards"):
                    creative_result = await self._create_carousel_creative(creative_data)
                else:
                    creative_result = await self._create_ad_creative(creative_data)
                results["steps"].append({"step": "creative", "result": creative_result})
                if creative_result.get("status") != "success":
                    results["status"] = "partial"
                    continue

                # Create ad linking creative to adset
                ad_result = await self._create_ad({
                    "adset_id": adset_id,
                    "creative_id": creative_result["creative_id"],
                    "name": creative_data.get("ad_name", creative_data.get("name", "AI Ad")),
                })
                results["steps"].append({"step": "ad", "result": ad_result})
                if ad_result.get("status") != "success":
                    results["status"] = "partial"

        return results
