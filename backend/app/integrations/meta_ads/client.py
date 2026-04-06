"""
Meta Marketing API Client — campaigns, ad sets, ads, insights, audiences.

Uses Meta Marketing API v22.0 for:
- Reading campaign/adset/ad structure and performance
- Creating and updating campaigns, ad sets, ads
- Reading audience insights and reach estimates
- Managing ad creatives
- Image/video ad upload
- Carousel ads, Stories, Reels placements

Meta Ad Creation Requirements (enforced per Meta docs):
- Campaign: name, objective (OUTCOME_*), status, special_ad_categories (REQUIRED — use ["NONE"] if N/A)
- Ad Set: campaign_id, name, billing_event, optimization_goal, targeting (geo_locations REQUIRED),
           daily_budget or lifetime_budget (lifetime requires end_time)
- Creative: page_id REQUIRED, object_story_spec with proper format
- Ad: adset_id, creative (as {"creative_id": "..."} JSON), status
- Images: upload via /adimages first, reference by image_hash in creatives
- Instagram: requires instagram_user_id (instagram_actor_id DEPRECATED since v22.0, removed Sept 2025)
- Special Ad Categories: MUST declare — housing/credit/employment restrict targeting (15mi min radius, no zip, no age/gender narrow)
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog
import httpx

from app.core.config import settings
from app.core.security import decrypt_token

logger = structlog.get_logger()

META_API_BASE = "https://graph.facebook.com/v22.0"

# Meta-required image specs
META_IMAGE_SPECS = {
    "feed": {"min_width": 600, "recommended": "1080x1080", "ratio": "1:1", "max_file_size_mb": 30},
    "stories": {"recommended": "1080x1920", "ratio": "9:16", "max_file_size_mb": 30},
    "reels": {"recommended": "1080x1920", "ratio": "9:16", "max_file_size_mb": 4000},  # video
    "right_column": {"recommended": "1200x628", "ratio": "1.91:1", "max_file_size_mb": 30},
    "carousel": {"recommended": "1080x1080", "ratio": "1:1", "max_cards": 10, "min_cards": 2},
}

# Valid Meta campaign objectives (API v21.0)
VALID_OBJECTIVES = [
    "OUTCOME_AWARENESS",
    "OUTCOME_ENGAGEMENT",
    "OUTCOME_LEADS",
    "OUTCOME_SALES",
    "OUTCOME_TRAFFIC",
    "OUTCOME_APP_PROMOTION",
]

# Valid optimization goals
VALID_OPTIMIZATION_GOALS = [
    "NONE", "APP_INSTALLS", "AD_RECALL_LIFT", "CLICKS", "ENGAGED_USERS",
    "EVENT_RESPONSES", "IMPRESSIONS", "LEAD_GENERATION", "QUALITY_LEAD",
    "LINK_CLICKS", "OFFSITE_CONVERSIONS", "PAGE_LIKES", "POST_ENGAGEMENT",
    "QUALITY_CALL", "REACH", "LANDING_PAGE_VIEWS", "VISIT_INSTAGRAM_PROFILE",
    "VALUE", "THRUPLAY", "DERIVED_EVENTS", "CONVERSATIONS",
]

# Valid CTA types
VALID_CTA_TYPES = [
    "LEARN_MORE", "SHOP_NOW", "SIGN_UP", "BOOK_NOW", "CONTACT_US",
    "CALL_NOW", "GET_QUOTE", "APPLY_NOW", "DOWNLOAD", "GET_OFFER",
    "GET_DIRECTIONS", "MESSAGE_PAGE", "SUBSCRIBE", "WATCH_MORE",
    "WHATSAPP_MESSAGE", "ORDER_NOW", "REQUEST_TIME", "SEE_MENU",
    "SEND_MESSAGE", "LISTEN_NOW", "OPEN_LINK", "NO_BUTTON",
]

# Valid special ad categories (Meta REQUIRES this field on every campaign)
VALID_SPECIAL_AD_CATEGORIES = [
    "NONE",
    "HOUSING",
    "CREDIT",
    "EMPLOYMENT",
    "ISSUES_ELECTIONS_POLITICS",
    "ONLINE_GAMBLING_AND_GAMING",
    "FINANCIAL_PRODUCTS_SERVICES",
]


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
                error_data = {}
                try:
                    error_data = resp.json().get("error", {})
                except Exception:
                    pass
                error = error_data.get("message", resp.text[:200])
                error_code = error_data.get("code", "unknown")
                error_subcode = error_data.get("error_subcode", "")
                logger.error("Meta API GET error", path=path, error=error,
                    code=error_code, subcode=error_subcode)
                return {"error": error, "error_code": error_code, "error_subcode": error_subcode}

    async def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST request to Meta API."""
        data["access_token"] = self._access_token
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{META_API_BASE}/{path}",
                data=data,
            )
            if resp.status_code in (200, 201):
                return resp.json()
            else:
                error_data = {}
                try:
                    error_data = resp.json().get("error", {})
                except Exception:
                    pass
                error = error_data.get("message", resp.text[:200])
                error_code = error_data.get("code", "unknown")
                error_subcode = error_data.get("error_subcode", "")
                logger.error("Meta API POST error", path=path, error=error,
                    code=error_code, subcode=error_subcode, data_keys=list(data.keys()))
                return {"error": error, "error_code": error_code, "error_subcode": error_subcode}

    # ── Account Info ───────────────────────────────────────────

    async def get_account_info(self) -> Dict[str, Any]:
        """Get ad account details including Instagram actor."""
        return await self._get(
            self._act,
            {"fields": "name,account_id,account_status,currency,timezone_name,amount_spent,balance,spend_cap,business,instagram_accounts{id,username},funding_source_details"},
        )

    async def get_instagram_accounts(self) -> List[Dict[str, Any]]:
        """Get Instagram accounts linked to this ad account."""
        result = await self._get(
            f"{self._act}/instagram_accounts",
            {"fields": "id,username,profile_pic,follower_count"},
        )
        return result.get("data", []) if "error" not in result else []

    # ── Campaigns ──────────────────────────────────────────────

    async def get_campaigns(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List campaigns with basic info."""
        params = {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time,created_time,updated_time,special_ad_categories,buying_type",
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
            "fields": "id,name,status,daily_budget,lifetime_budget,optimization_goal,billing_event,targeting,start_time,end_time,promoted_object,destination_type",
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
            "fields": "id,name,status,creative{id,name,title,body,image_url,thumbnail_url,call_to_action_type,link_url,object_story_spec},created_time",
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

    # ── Image Upload ──────────────────────────────────────────

    async def upload_ad_image(self, image_url: str, name: str = "Ad Image") -> Dict[str, Any]:
        """
        Upload an image to Meta's ad image library via URL.
        Returns image_hash which is needed for creating creatives.
        Meta REQUIRES images to be uploaded first, then referenced by hash.
        """
        result = await self._post(f"{self._act}/adimages", {
            "url": image_url,
            "name": name,
        })
        if "error" in result:
            return result
        # Extract image hash from response
        images = result.get("images", {})
        if images:
            first_key = list(images.keys())[0]
            return {
                "image_hash": images[first_key].get("hash"),
                "image_url": images[first_key].get("url"),
                "name": name,
            }
        return result

    async def upload_ad_image_bytes(self, image_bytes: bytes, name: str = "Ad Image") -> Dict[str, Any]:
        """Upload raw image bytes to Meta's ad image library."""
        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        result = await self._post(f"{self._act}/adimages", {
            "bytes": b64,
            "name": name,
        })
        if "error" in result:
            return result
        images = result.get("images", {})
        if images:
            first_key = list(images.keys())[0]
            return {
                "image_hash": images[first_key].get("hash"),
                "image_url": images[first_key].get("url"),
                "name": name,
            }
        return result

    # ── Write Operations ───────────────────────────────────────

    async def create_campaign(
        self, name: str, objective: str = "OUTCOME_LEADS",
        daily_budget: int = 2000, status: str = "PAUSED",
        special_ad_categories: Optional[List[str]] = None,
        special_ad_category_country: Optional[List[str]] = None,
        buying_type: str = "AUCTION",
    ) -> Dict[str, Any]:
        """
        Create a campaign. Budget in cents.
        Meta REQUIRES special_ad_categories — use ["NONE"] for normal ads.
        special_ad_category_country REQUIRED when special_ad_categories contains
        HOUSING, CREDIT, or EMPLOYMENT (e.g., ["US", "CA"]).
        """
        if objective not in VALID_OBJECTIVES:
            return {"error": f"Invalid objective '{objective}'. Valid: {VALID_OBJECTIVES}"}

        # Meta requires this field — default to ["NONE"] if not specified
        categories = special_ad_categories if special_ad_categories else ["NONE"]

        # Validate: special_ad_category_country required for restricted categories
        restricted = {"HOUSING", "CREDIT", "EMPLOYMENT"}
        has_restricted = any(c in restricted for c in categories)
        if has_restricted and not special_ad_category_country:
            special_ad_category_country = ["US"]  # safe default
            logger.warning("Auto-defaulting special_ad_category_country to ['US'] for restricted category")

        data: Dict[str, Any] = {
            "name": name,
            "objective": objective,
            "status": status,
            "daily_budget": str(daily_budget),
            "special_ad_categories": json.dumps(categories),
            "buying_type": buying_type,
        }
        if special_ad_category_country:
            data["special_ad_category_country"] = json.dumps(special_ad_category_country)

        return await self._post(f"{self._act}/campaigns", data)

    async def update_campaign_status(self, campaign_id: str, status: str) -> Dict[str, Any]:
        """Pause or activate a campaign. Status: ACTIVE, PAUSED."""
        return await self._post(campaign_id, {"status": status})

    async def update_campaign_budget(self, campaign_id: str, daily_budget: int) -> Dict[str, Any]:
        """Update campaign daily budget in cents."""
        return await self._post(campaign_id, {"daily_budget": str(daily_budget)})

    async def create_adset(
        self, campaign_id: str, name: str, daily_budget: int = 2000,
        optimization_goal: str = "LEAD_GENERATION", billing_event: str = "IMPRESSIONS",
        targeting: Optional[Dict] = None, status: str = "PAUSED",
        start_time: Optional[str] = None, end_time: Optional[str] = None,
        lifetime_budget: Optional[int] = None,
        promoted_object: Optional[Dict] = None,
        destination_type: Optional[str] = None,
        bid_amount: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create an ad set with proper Meta-required fields.
        targeting MUST include geo_locations and age_min/age_max at minimum.
        When using lifetime_budget, end_time is REQUIRED by Meta.
        """
        if optimization_goal not in VALID_OPTIMIZATION_GOALS:
            return {"error": f"Invalid optimization_goal '{optimization_goal}'. Valid: {VALID_OPTIMIZATION_GOALS}"}

        # Validate: lifetime_budget requires end_time
        if lifetime_budget and not end_time:
            return {"error": "end_time is REQUIRED when using lifetime_budget (Meta requirement)"}

        # Ensure minimum targeting (Meta requires geo_locations)
        if not targeting:
            targeting = {
                "geo_locations": {"countries": ["US"]},
                "age_min": 18,
                "age_max": 65,
            }
        elif "geo_locations" not in targeting:
            targeting["geo_locations"] = {"countries": ["US"]}

        data: Dict[str, Any] = {
            "campaign_id": campaign_id,
            "name": name,
            "optimization_goal": optimization_goal,
            "billing_event": billing_event,
            "status": status,
            "targeting": json.dumps(targeting),
        }

        # Budget: use lifetime_budget if provided, otherwise daily_budget
        if lifetime_budget:
            data["lifetime_budget"] = str(lifetime_budget)
        else:
            data["daily_budget"] = str(daily_budget)

        if start_time:
            data["start_time"] = start_time
        if end_time:
            data["end_time"] = end_time
        if promoted_object:
            data["promoted_object"] = json.dumps(promoted_object)
        if destination_type:
            data["destination_type"] = destination_type
        if bid_amount:
            data["bid_amount"] = str(bid_amount)

        return await self._post(f"{self._act}/adsets", data)

    async def create_ad(
        self, adset_id: str, name: str, creative_id: str, status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """Create an ad linking to an existing creative."""
        return await self._post(f"{self._act}/ads", {
            "name": name,
            "adset_id": adset_id,
            "creative": json.dumps({"creative_id": creative_id}),
            "status": status,
        })

    async def create_ad_creative(
        self, name: str, page_id: str, message: str,
        link: Optional[str] = None, image_url: Optional[str] = None,
        image_hash: Optional[str] = None,
        call_to_action_type: str = "LEARN_MORE",
        headline: Optional[str] = None,
        description: Optional[str] = None,
        instagram_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create an ad creative with proper Meta format.

        Meta Requirements:
        - page_id is REQUIRED (Facebook Page must be connected)
        - For link ads: link is required in link_data
        - For image ads: use image_hash (upload first via upload_ad_image)
          or image_url (Meta will fetch it, but image_hash is more reliable)
        - call_to_action requires a link
        - headline: shown below image (25 chars recommended)
        - description: shown below headline in some placements
        - instagram_user_id: required for Instagram placements
        """
        if call_to_action_type not in VALID_CTA_TYPES:
            call_to_action_type = "LEARN_MORE"

        link_data: Dict[str, Any] = {
            "message": message,
        }
        if link:
            link_data["link"] = link
            link_data["call_to_action"] = {"type": call_to_action_type, "value": {"link": link}}
        else:
            link_data["call_to_action"] = {"type": call_to_action_type}

        if image_hash:
            link_data["image_hash"] = image_hash
        elif image_url:
            link_data["image_url"] = image_url

        if headline:
            link_data["name"] = headline  # Meta calls headline "name" in link_data
        if description:
            link_data["description"] = description

        object_story: Dict[str, Any] = {
            "page_id": page_id,
            "link_data": link_data,
        }
        if instagram_user_id:
            object_story["instagram_user_id"] = instagram_user_id

        data: Dict[str, Any] = {
            "name": name,
            "object_story_spec": json.dumps(object_story),
        }
        return await self._post(f"{self._act}/adcreatives", data)

    async def create_carousel_creative(
        self, name: str, page_id: str, message: str,
        cards: List[Dict[str, Any]], link: str,
        call_to_action_type: str = "LEARN_MORE",
        instagram_user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a carousel ad creative (2-10 cards).
        Each card: {"name": headline, "description": ..., "image_hash": ..., "link": ...}
        """
        if len(cards) < 2:
            return {"error": "Carousel requires at least 2 cards"}
        if len(cards) > 10:
            cards = cards[:10]

        child_attachments = []
        for card in cards:
            child = {
                "link": card.get("link", link),
                "call_to_action": {"type": call_to_action_type, "value": {"link": card.get("link", link)}},
            }
            if card.get("name"):
                child["name"] = card["name"]
            if card.get("description"):
                child["description"] = card["description"]
            if card.get("image_hash"):
                child["image_hash"] = card["image_hash"]
            elif card.get("image_url"):
                child["picture"] = card["image_url"]
            child_attachments.append(child)

        object_story: Dict[str, Any] = {
            "page_id": page_id,
            "link_data": {
                "message": message,
                "link": link,
                "child_attachments": child_attachments,
            },
        }
        if instagram_user_id:
            object_story["instagram_user_id"] = instagram_user_id

        return await self._post(f"{self._act}/adcreatives", {
            "name": name,
            "object_story_spec": json.dumps(object_story),
        })

    # ── Audiences ──────────────────────────────────────────────

    async def get_custom_audiences(self) -> List[Dict[str, Any]]:
        """List custom audiences."""
        params = {"fields": "id,name,subtype,approximate_count,delivery_status"}
        result = await self._get(f"{self._act}/customaudiences", params)
        return result.get("data", []) if "error" not in result else []

    async def get_targeting_search(self, query: str, target_type: str = "adinterest") -> List[Dict[str, Any]]:
        """Search for targeting options (interests, behaviors, demographics)."""
        result = await self._get("search", {
            "type": target_type,
            "q": query,
            "limit": 25,
        })
        return result.get("data", []) if "error" not in result else []

    # ── Ad Previews ───────────────────────────────────────────

    async def get_ad_preview(self, creative_id: str, ad_format: str = "DESKTOP_FEED_STANDARD") -> Dict[str, Any]:
        """Get an ad preview for a creative."""
        return await self._get(f"{self._act}/generatepreviews", {
            "creative": json.dumps({"creative_id": creative_id}),
            "ad_format": ad_format,
        })

    # ── Audit / Analysis ───────────────────────────────────────

    async def build_full_context(self, date_from: Optional[str] = None, date_to: Optional[str] = None) -> Dict[str, Any]:
        """Build complete account context for Claude analysis."""
        account = await self.get_account_info()
        campaigns = await self.get_campaigns()
        performance = await self.get_all_campaign_performance(date_from, date_to)
        audiences = await self.get_custom_audiences()
        instagram_accounts = await self.get_instagram_accounts()

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
            "instagram_accounts": instagram_accounts,
            "heuristics": {
                "total_spend": round(total_spend, 2),
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "total_reach": total_reach,
                "avg_cpc": round(total_spend / total_clicks, 2) if total_clicks > 0 else 0,
                "avg_ctr": round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0,
                "campaign_count": len(campaigns),
                "active_campaigns": len([c for c in campaigns if c.get("status") == "ACTIVE"]),
                "has_instagram": len(instagram_accounts) > 0,
            },
        }
