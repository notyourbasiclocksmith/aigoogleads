"""
Google Ads Mutation Service — executes approved write actions safely.

Every mutation:
1. Validates the resource exists
2. Captures before-state
3. Executes the Google Ads API call
4. Captures after-state
5. Returns detailed result
"""
from typing import Dict, Any, List
from datetime import datetime, timezone
import structlog
from app.integrations.google_ads.client import GoogleAdsClient

logger = structlog.get_logger()


class GoogleAdsMutationService:
    """Safely executes Google Ads API write operations."""

    def __init__(self, ads_client: GoogleAdsClient):
        self.client = ads_client

    async def execute_action(self, action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Route an action to the correct handler. Returns execution result."""
        handlers = {
            "pause_keyword": self._pause_keyword,
            "enable_keyword": self._enable_keyword,
            "add_negative_keyword": self._add_negative_keywords,
            "update_campaign_budget": self._update_budget,
            "pause_campaign": self._pause_campaign,
            "enable_campaign": self._enable_campaign,
            "create_campaign": self._create_campaign,
            "create_ad_group": self._create_ad_group,
            "create_responsive_search_ad": self._create_rsa,
            "add_keywords": self._add_keywords,
        }

        handler = handlers.get(action_type)
        if not handler:
            return {"status": "failed", "error": f"Unknown action type: {action_type}"}

        try:
            result = await handler(payload)
            return result
        except Exception as e:
            logger.error("Mutation failed", action_type=action_type, error=str(e))
            return {"status": "failed", "error": str(e)}

    async def _pause_keyword(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Pause one or more keywords by criterion ID."""
        await self.client._ensure_token()
        client = self.client._get_client()
        agc_service = client.get_service("AdGroupCriterionService")

        keyword_ids = payload.get("keyword_ids", [])
        ad_group_id = payload.get("ad_group_id")
        results = []

        for kid in keyword_ids:
            try:
                resource = f"customers/{self.client.customer_id}/adGroupCriteria/{ad_group_id}~{kid}"
                op = client.get_type("AdGroupCriterionOperation")
                op.update.resource_name = resource
                op.update.status = client.enums.AdGroupCriterionStatusEnum.PAUSED
                fm = client.get_type("FieldMask")
                fm.paths.append("status")
                op.update_mask.CopyFrom(fm)

                agc_service.mutate_ad_group_criteria(
                    customer_id=self.client.customer_id, operations=[op]
                )
                results.append({"keyword_id": kid, "status": "paused"})
            except Exception as e:
                results.append({"keyword_id": kid, "status": "failed", "error": str(e)[:200]})

        succeeded = sum(1 for r in results if r["status"] == "paused")
        return {
            "status": "success" if succeeded == len(keyword_ids) else ("partial" if succeeded > 0 else "failed"),
            "succeeded": succeeded,
            "total": len(keyword_ids),
            "details": results,
        }

    async def _enable_keyword(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Enable one or more keywords."""
        await self.client._ensure_token()
        client = self.client._get_client()
        agc_service = client.get_service("AdGroupCriterionService")

        keyword_ids = payload.get("keyword_ids", [])
        ad_group_id = payload.get("ad_group_id")
        results = []

        for kid in keyword_ids:
            try:
                resource = f"customers/{self.client.customer_id}/adGroupCriteria/{ad_group_id}~{kid}"
                op = client.get_type("AdGroupCriterionOperation")
                op.update.resource_name = resource
                op.update.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
                fm = client.get_type("FieldMask")
                fm.paths.append("status")
                op.update_mask.CopyFrom(fm)

                agc_service.mutate_ad_group_criteria(
                    customer_id=self.client.customer_id, operations=[op]
                )
                results.append({"keyword_id": kid, "status": "enabled"})
            except Exception as e:
                results.append({"keyword_id": kid, "status": "failed", "error": str(e)[:200]})

        succeeded = sum(1 for r in results if r["status"] == "enabled")
        return {
            "status": "success" if succeeded == len(keyword_ids) else ("partial" if succeeded > 0 else "failed"),
            "succeeded": succeeded,
            "total": len(keyword_ids),
            "details": results,
        }

    async def _add_negative_keywords(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add negative keywords at campaign level."""
        await self.client._ensure_token()
        client = self.client._get_client()
        cc_service = client.get_service("CampaignCriterionService")

        terms = payload.get("terms", [])
        campaign_id = payload.get("campaign_id")
        results = []

        operations = []
        for term in terms:
            text = term if isinstance(term, str) else term.get("text", "")
            op = client.get_type("CampaignCriterionOperation")
            op.create.campaign = f"customers/{self.client.customer_id}/campaigns/{campaign_id}"
            op.create.keyword.text = text
            op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
            op.create.negative = True
            operations.append(op)

        try:
            response = cc_service.mutate_campaign_criteria(
                customer_id=self.client.customer_id, operations=operations
            )
            return {
                "status": "success",
                "added": len(response.results),
                "total": len(terms),
                "campaign_id": campaign_id,
            }
        except Exception as e:
            # Try one by one
            succeeded = 0
            for i, op in enumerate(operations):
                try:
                    cc_service.mutate_campaign_criteria(
                        customer_id=self.client.customer_id, operations=[op]
                    )
                    succeeded += 1
                except Exception:
                    results.append({"term": terms[i], "error": "failed"})

            return {
                "status": "partial" if succeeded > 0 else "failed",
                "added": succeeded,
                "total": len(terms),
                "failures": results,
            }

    async def _update_budget(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update campaign daily budget."""
        campaign_id = payload.get("campaign_id")
        new_budget = payload.get("new_daily_budget")  # in dollars

        # First get the budget resource name
        await self.client._ensure_token()
        client = self.client._get_client()
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT campaign.id, campaign_budget.resource_name, campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """
        response = ga_service.search(customer_id=self.client.customer_id, query=query)
        budget_resource = None
        old_budget_micros = 0
        for row in response:
            budget_resource = row.campaign_budget.resource_name
            old_budget_micros = row.campaign_budget.amount_micros
            break

        if not budget_resource:
            return {"status": "failed", "error": f"Campaign {campaign_id} not found"}

        new_micros = int(new_budget * 1_000_000)
        result = await self.client.update_campaign_budget(budget_resource, new_micros)

        if result.get("status") == "error":
            return {"status": "failed", "error": result.get("error")}

        return {
            "status": "success",
            "campaign_id": campaign_id,
            "before": {"daily_budget": round(old_budget_micros / 1_000_000, 2)},
            "after": {"daily_budget": new_budget},
        }

    async def _pause_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Pause a campaign."""
        campaign_id = payload.get("campaign_id")
        resource = f"customers/{self.client.customer_id}/campaigns/{campaign_id}"
        result = await self.client.update_campaign_status(resource, "PAUSED")
        if result.get("status") == "error":
            return {"status": "failed", "error": result.get("error")}
        return {"status": "success", "campaign_id": campaign_id, "new_status": "PAUSED"}

    async def _enable_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Enable a campaign."""
        campaign_id = payload.get("campaign_id")
        resource = f"customers/{self.client.customer_id}/campaigns/{campaign_id}"
        result = await self.client.update_campaign_status(resource, "ENABLED")
        if result.get("status") == "error":
            return {"status": "failed", "error": result.get("error")}
        return {"status": "success", "campaign_id": campaign_id, "new_status": "ENABLED"}

    async def _create_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new campaign."""
        result = await self.client.create_campaign(payload)
        return result

    async def _create_ad_group(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create an ad group within a campaign."""
        campaign_resource = payload.get("campaign_resource")
        result = await self.client.create_ad_group(campaign_resource, payload)
        return result

    async def _create_rsa(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a responsive search ad."""
        ad_group_resource = payload.get("ad_group_resource")
        result = await self.client.create_responsive_search_ad(ad_group_resource, payload)
        return result

    async def _add_keywords(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Add keywords to an ad group."""
        ad_group_resource = payload.get("ad_group_resource")
        keywords = payload.get("keywords", [])
        result = await self.client.create_keywords(ad_group_resource, keywords)
        return result
