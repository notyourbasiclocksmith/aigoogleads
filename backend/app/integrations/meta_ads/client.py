"""
Meta Marketing API Client — campaigns, ad sets, ads, insights, audiences.

Uses Meta Marketing API v21.0 for:
- Reading campaign/adset/ad structure and performance
- Creating and updating campaigns, ad sets, ads
- Reading audience insights and reach estimates
- Managing ad creatives
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog
import httpx

from app.core.config import settings
from app.core.security import decrypt_token

logger = structlog.get_logger()

META_API_BASE = "https://graph.facebook.com/v21.0"


class MetaAdsClient:
    """Meta Marketing API client for a single ad account."""

    def __init__(self, ad_account_id: str, access_token_encrypted: str):
        self.ad_account_id = ad_account_id
        self._access_token = decrypt_token(access_token_encrypted)

    @property
    def _act(self) -> str:
        """Prefixed ad account ID."""
        return f"act_{self.ad_account_id}" if not self.ad_account_id.startswith("act_") else self.ad_account_id

    def _params(self, extra: Optional[Dict] = None) -> Dict[str, Any]:
        p = {"access_token": self._access_token}
        if extra:
            p.update(extra)
        return p

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """GET request to Meta API."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{META_API_BASE}/{path}",
                params=self._params(params),
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                error = resp.json().get("error", {}).get("message", resp.text[:200])
                logger.error("Meta API GET error", path=path, error=error)
                return {"error": error}

    async def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST request to Meta API."""
        data["access_token"] = self._access_token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{META_API_BASE}/{path}",
                data=data,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            else:
                error = resp.json().get("error", {}).get("message", resp.text[:200])
                logger.error("Meta API POST error", path=path, error=error)
                return {"error": error}

    # ── Account Info ───────────────────────────────────────────

    async def get_account_info(self) -> Dict[str, Any]:
        """Get ad account details."""
        return await self._get(
            self._act,
            {"fields": "name,account_id,account_status,currency,timezone_name,amount_spent,balance,spend_cap"},
        )

    # ── Campaigns ──────────────────────────────────────────────

    async def get_campaigns(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List campaigns with basic info."""
        params = {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time,created_time,updated_time",
            "limit": 100,
        }
        if status_filter:
            params["filtering"] = f'[{{"field":"status","operator":"EQUAL","value":"{status_filter}"}}]'
        result = await self._get(f"{self._act}/campaigns", params)
        return result.get("data", []) if "error" not in result else []

    async def get_campaign_insights(
        self, campaign_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get campaign performance metrics."""
        params = {
            "fields": "impressions,clicks,spend,reach,frequency,cpc,cpm,ctr,actions,cost_per_action_type,conversions,conversion_values",
            "date_preset": "last_30d",
        }
        if date_from and date_to:
            params.pop("date_preset", None)
            params["time_range"] = f'{{"since":"{date_from}","until":"{date_to}"}}'
        return await self._get(f"{campaign_id}/insights", params)

    async def get_all_campaign_performance(
        self, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get performance for all campaigns."""
        params = {
            "fields": "campaign_id,campaign_name,impressions,clicks,spend,reach,cpc,cpm,ctr,actions,conversions",
            "level": "campaign",
            "date_preset": "last_30d",
            "limit": 100,
        }
        if date_from and date_to:
            params.pop("date_preset", None)
            params["time_range"] = f'{{"since":"{date_from}","until":"{date_to}"}}'
        result = await self._get(f"{self._act}/insights", params)
        return result.get("data", []) if "error" not in result else []

    # ── Ad Sets ────────────────────────────────────────────────

    async def get_adsets(self, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List ad sets."""
        parent = campaign_id if campaign_id else self._act
        params = {
            "fields": "id,name,status,daily_budget,lifetime_budget,optimization_goal,billing_event,targeting,start_time,end_time",
            "limit": 100,
        }
        result = await self._get(f"{parent}/adsets", params)
        return result.get("data", []) if "error" not in result else []

    async def get_adset_insights(
        self, adset_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get ad set performance."""
        params = {
            "fields": "impressions,clicks,spend,reach,cpc,cpm,ctr,actions,conversions",
            "date_preset": "last_30d",
        }
        if date_from and date_to:
            params.pop("date_preset", None)
            params["time_range"] = f'{{"since":"{date_from}","until":"{date_to}"}}'
        return await self._get(f"{adset_id}/insights", params)

    # ── Ads ────────────────────────────────────────────────────

    async def get_ads(self, adset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List ads."""
        parent = adset_id if adset_id else self._act
        params = {
            "fields": "id,name,status,creative{id,name,title,body,image_url,thumbnail_url,call_to_action_type,link_url},created_time",
            "limit": 100,
        }
        result = await self._get(f"{parent}/ads", params)
        return result.get("data", []) if "error" not in result else []

    async def get_ad_insights(
        self, ad_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get ad-level performance."""
        params = {
            "fields": "impressions,clicks,spend,reach,cpc,cpm,ctr,actions,conversions",
            "date_preset": "last_30d",
        }
        if date_from and date_to:
            params.pop("date_preset", None)
            params["time_range"] = f'{{"since":"{date_from}","until":"{date_to}"}}'
        return await self._get(f"{ad_id}/insights", params)

    # ── Write Operations ───────────────────────────────────────

    async def create_campaign(
        self, name: str, objective: str = "OUTCOME_LEADS",
        daily_budget: int = 2000, status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """Create a campaign. Budget in cents."""
        return await self._post(f"{self._act}/campaigns", {
            "name": name,
            "objective": objective,
            "status": status,
            "daily_budget": daily_budget,
            "special_ad_categories": "[]",
        })

    async def update_campaign_status(self, campaign_id: str, status: str) -> Dict[str, Any]:
        """Pause or activate a campaign. Status: ACTIVE, PAUSED."""
        return await self._post(campaign_id, {"status": status})

    async def update_campaign_budget(self, campaign_id: str, daily_budget: int) -> Dict[str, Any]:
        """Update campaign daily budget in cents."""
        return await self._post(campaign_id, {"daily_budget": daily_budget})

    async def create_adset(
        self, campaign_id: str, name: str, daily_budget: int = 2000,
        optimization_goal: str = "LEAD_GENERATION", billing_event: str = "IMPRESSIONS",
        targeting: Optional[Dict] = None, status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """Create an ad set."""
        data = {
            "campaign_id": campaign_id,
            "name": name,
            "daily_budget": daily_budget,
            "optimization_goal": optimization_goal,
            "billing_event": billing_event,
            "status": status,
        }
        if targeting:
            import json
            data["targeting"] = json.dumps(targeting)
        return await self._post(f"{self._act}/adsets", data)

    async def create_ad(
        self, adset_id: str, name: str, creative_id: str, status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """Create an ad linking to an existing creative."""
        import json
        return await self._post(f"{self._act}/ads", {
            "name": name,
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": status,
        })

    async def create_ad_creative(
        self, name: str, page_id: str, message: str,
        link: Optional[str] = None, image_url: Optional[str] = None,
        call_to_action_type: str = "LEARN_MORE",
    ) -> Dict[str, Any]:
        """Create an ad creative."""
        import json
        data: Dict[str, Any] = {"name": name}
        object_story = {
            "page_id": page_id,
            "link_data": {
                "message": message,
                "call_to_action": {"type": call_to_action_type},
            },
        }
        if link:
            object_story["link_data"]["link"] = link
        if image_url:
            object_story["link_data"]["image_url"] = image_url
        data["object_story_spec"] = json.dumps(object_story)
        return await self._post(f"{self._act}/adcreatives", data)

    # ── Audiences ──────────────────────────────────────────────

    async def get_custom_audiences(self) -> List[Dict[str, Any]]:
        """List custom audiences."""
        params = {"fields": "id,name,subtype,approximate_count,delivery_status"}
        result = await self._get(f"{self._act}/customaudiences", params)
        return result.get("data", []) if "error" not in result else []

    # ── Audit / Analysis ───────────────────────────────────────

    async def build_full_context(self, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """Build complete account context for Claude analysis."""
        account = await self.get_account_info()
        campaigns = await self.get_campaigns()
        performance = await self.get_all_campaign_performance(date_from, date_to)
        audiences = await self.get_custom_audiences()

        # Compute heuristics
        total_spend = sum(float(p.get("spend", 0)) for p in performance)
        total_clicks = sum(int(p.get("clicks", 0)) for p in performance)
        total_impressions = sum(int(p.get("impressions", 0)) for p in performance)
        total_reach = sum(int(p.get("reach", 0)) for p in performance)

        return {
            "platform": "meta",
            "account": account,
            "campaigns": campaigns,
            "performance": performance,
            "audiences": audiences,
            "heuristics": {
                "total_spend": round(total_spend, 2),
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "total_reach": total_reach,
                "avg_cpc": round(total_spend / total_clicks, 2) if total_clicks > 0 else 0,
                "avg_ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
                "campaign_count": len(campaigns),
                "active_campaigns": len([c for c in campaigns if c.get("status") == "ACTIVE"]),
            },
        }
