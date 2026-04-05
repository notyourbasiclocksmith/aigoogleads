"""
Google Business Profile API Client — reviews, posts, business info, review responses.

Uses Google My Business API (v4) / Business Profile API for:
- Reading and responding to reviews
- Creating and managing posts (updates, offers, events)
- Reading business information and insights
- Managing photos
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import structlog
import httpx

from app.core.config import settings
from app.core.security import decrypt_token

logger = structlog.get_logger()

GBP_API_BASE = "https://mybusiness.googleapis.com/v4"
GBP_API_V1 = "https://mybusinessbusinessinformation.googleapis.com/v1"


class GBPClient:
    """Google Business Profile API client."""

    def __init__(self, account_id: str, location_id: str, refresh_token_encrypted: str):
        self.account_id = account_id
        self.location_id = location_id
        self._refresh_token = decrypt_token(refresh_token_encrypted)
        self._access_token: Optional[str] = None

    @property
    def _location_name(self) -> str:
        return f"accounts/{self.account_id}/locations/{self.location_id}"

    async def _ensure_token(self):
        """Refresh OAuth token."""
        if self._access_token:
            return
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": settings.GA4_CLIENT_ID,
                    "client_secret": settings.GA4_CLIENT_SECRET,
                },
            )
            if resp.status_code == 200:
                self._access_token = resp.json()["access_token"]
            else:
                raise Exception(f"GBP token refresh failed: {resp.text[:200]}")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    # ── Reviews ─────────────────────────────────────────────────

    async def get_reviews(self, page_size: int = 50, page_token: Optional[str] = None) -> Dict[str, Any]:
        """Fetch reviews for the location."""
        await self._ensure_token()
        params = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GBP_API_BASE}/{self._location_name}/reviews",
                headers=self._headers(),
                params=params,
            )
            if resp.status_code == 200:
                data = resp.json()
                reviews = []
                for r in data.get("reviews", []):
                    reviews.append({
                        "review_id": r.get("reviewId"),
                        "reviewer_name": r.get("reviewer", {}).get("displayName"),
                        "star_rating": r.get("starRating"),
                        "comment": r.get("comment", ""),
                        "create_time": r.get("createTime"),
                        "update_time": r.get("updateTime"),
                        "reply": r.get("reviewReply", {}).get("comment") if r.get("reviewReply") else None,
                        "reply_time": r.get("reviewReply", {}).get("updateTime") if r.get("reviewReply") else None,
                    })
                return {
                    "reviews": reviews,
                    "count": len(reviews),
                    "total_review_count": data.get("totalReviewCount", 0),
                    "average_rating": data.get("averageRating", 0),
                    "next_page_token": data.get("nextPageToken"),
                }
            else:
                return {"reviews": [], "error": resp.text[:200]}

    async def reply_to_review(self, review_id: str, reply_text: str) -> Dict[str, Any]:
        """Reply to a specific review."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{GBP_API_BASE}/{self._location_name}/reviews/{review_id}/reply",
                headers=self._headers(),
                json={"comment": reply_text},
            )
            if resp.status_code == 200:
                return {"status": "replied", "review_id": review_id, "reply": reply_text}
            else:
                return {"status": "error", "error": resp.text[:200]}

    async def delete_review_reply(self, review_id: str) -> Dict[str, Any]:
        """Delete a reply from a review."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{GBP_API_BASE}/{self._location_name}/reviews/{review_id}/reply",
                headers=self._headers(),
            )
            if resp.status_code in (200, 204):
                return {"status": "deleted", "review_id": review_id}
            else:
                return {"status": "error", "error": resp.text[:200]}

    # ── Posts ───────────────────────────────────────────────────

    async def get_posts(self, page_size: int = 20) -> Dict[str, Any]:
        """Fetch local posts."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GBP_API_BASE}/{self._location_name}/localPosts",
                headers=self._headers(),
                params={"pageSize": page_size},
            )
            if resp.status_code == 200:
                data = resp.json()
                posts = []
                for p in data.get("localPosts", []):
                    posts.append({
                        "post_id": p.get("name", "").split("/")[-1],
                        "name": p.get("name"),
                        "summary": p.get("summary", ""),
                        "topic_type": p.get("topicType"),
                        "state": p.get("state"),
                        "create_time": p.get("createTime"),
                        "update_time": p.get("updateTime"),
                        "media": [{"url": m.get("googleUrl"), "format": m.get("mediaFormat")} for m in p.get("media", [])],
                        "call_to_action": p.get("callToAction"),
                        "event": p.get("event"),
                        "offer": p.get("offer"),
                    })
                return {"posts": posts, "count": len(posts)}
            else:
                return {"posts": [], "error": resp.text[:200]}

    async def create_post(
        self,
        summary: str,
        topic_type: str = "STANDARD",
        media_url: Optional[str] = None,
        call_to_action_type: Optional[str] = None,
        call_to_action_url: Optional[str] = None,
        offer_coupon: Optional[str] = None,
        event_title: Optional[str] = None,
        event_start: Optional[str] = None,
        event_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a local post.
        topic_type: STANDARD, EVENT, OFFER
        call_to_action_type: BOOK, ORDER, SHOP, LEARN_MORE, SIGN_UP, CALL
        """
        await self._ensure_token()
        body: Dict[str, Any] = {
            "summary": summary,
            "topicType": topic_type,
            "languageCode": "en-US",
        }

        if media_url:
            body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": media_url}]

        if call_to_action_type and call_to_action_url:
            body["callToAction"] = {
                "actionType": call_to_action_type,
                "url": call_to_action_url,
            }

        if topic_type == "OFFER" and offer_coupon:
            body["offer"] = {"couponCode": offer_coupon}

        if topic_type == "EVENT" and event_title:
            body["event"] = {"title": event_title}
            if event_start:
                body["event"]["schedule"] = {"startDate": self._parse_date(event_start)}
                if event_end:
                    body["event"]["schedule"]["endDate"] = self._parse_date(event_end)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GBP_API_BASE}/{self._location_name}/localPosts",
                headers=self._headers(),
                json=body,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {"status": "created", "post_name": data.get("name"), "summary": summary}
            else:
                return {"status": "error", "error": resp.text[:200]}

    async def delete_post(self, post_name: str) -> Dict[str, Any]:
        """Delete a local post."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                f"{GBP_API_BASE}/{post_name}",
                headers=self._headers(),
            )
            if resp.status_code in (200, 204):
                return {"status": "deleted", "post_name": post_name}
            else:
                return {"status": "error", "error": resp.text[:200]}

    # ── Business Info ──────────────────────────────────────────

    async def get_business_info(self) -> Dict[str, Any]:
        """Get location details."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GBP_API_V1}/{self._location_name}",
                headers=self._headers(),
                params={"readMask": "name,title,phoneNumbers,categories,storefrontAddress,websiteUri,regularHours,profile"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "name": data.get("name"),
                    "title": data.get("title"),
                    "phone": data.get("phoneNumbers", {}).get("primaryPhone"),
                    "website": data.get("websiteUri"),
                    "address": data.get("storefrontAddress"),
                    "categories": data.get("categories"),
                    "hours": data.get("regularHours"),
                    "description": data.get("profile", {}).get("description"),
                }
            else:
                return {"error": resp.text[:200]}

    # ── Insights ───────────────────────────────────────────────

    async def get_insights(self, date_from: str, date_to: str) -> Dict[str, Any]:
        """Get performance insights (views, searches, actions)."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GBP_API_BASE}/{self._location_name}:reportInsights",
                headers=self._headers(),
                json={
                    "locationNames": [self._location_name],
                    "basicRequest": {
                        "metricRequests": [
                            {"metric": "ALL"},
                        ],
                        "timeRange": {
                            "startTime": f"{date_from}T00:00:00Z",
                            "endTime": f"{date_to}T23:59:59Z",
                        },
                    },
                },
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                return {"error": resp.text[:200]}

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str) -> Dict[str, int]:
        """Parse 'YYYY-MM-DD' into GBP date object."""
        parts = date_str.split("-")
        return {"year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])}
