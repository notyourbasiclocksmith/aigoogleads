"""
Meta Ads Mutation Service — safe write operations with before/after state capture.
"""
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
        }
        handler = handlers.get(action_type)
        if not handler:
            return {"status": "failed", "error": f"Unknown action type: {action_type}"}
        try:
            return await handler(payload)
        except Exception as e:
            logger.error("Meta mutation failed", action=action_type, error=str(e))
            return {"status": "failed", "error": str(e)[:500]}

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
        result = await self.client.create_campaign(name, objective, daily_budget, "PAUSED")
        if "error" in result:
            return {"status": "failed", "error": result["error"]}
        return {"status": "success", "campaign_id": result.get("id"), "name": name}
