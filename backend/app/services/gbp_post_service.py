"""
Google Business Profile Post Service.
Create, publish, schedule, and auto-generate GBP posts.
Includes AI-powered post generation from campaign data.
"""
import json
import re
import structlog
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.gbp_location import GBPLocation
from app.models.gbp_post import GBPPost, GBPPostStatus, GBPPostType, GBPPostTemplate
from app.models.business_profile import BusinessProfile
from app.services import gbp_oauth_service

logger = structlog.get_logger()

GBP_API_BASE = "https://mybusiness.googleapis.com/v4"
MAX_POST_LENGTH = 1500
OPTIMAL_LENGTH = (90, 300)


class GBPPostService:
    """Manage GBP posts: CRUD, publish, schedule, AI generation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Create Post ─────────────────────────────────────────────────

    async def create_post(
        self,
        tenant_id: str,
        location_id: str,
        content: str,
        post_type: str = "UPDATE",
        media_url: Optional[str] = None,
        call_to_action: str = "LEARN_MORE",
        cta_url: Optional[str] = None,
        title: Optional[str] = None,
    ) -> GBPPost:
        """Create a draft GBP post."""
        if len(content) > MAX_POST_LENGTH:
            content = content[: MAX_POST_LENGTH - 3] + "..."

        post = GBPPost(
            tenant_id=tenant_id,
            location_id=location_id,
            post_type=GBPPostType[post_type.upper()],
            title=title,
            summary=content,
            media_url=media_url,
            call_to_action=call_to_action,
            cta_url=cta_url,
            status=GBPPostStatus.DRAFT,
            auto_generated=False,
        )
        self.db.add(post)
        await self.db.flush()
        return post

    # ── Publish Post ────────────────────────────────────────────────

    async def publish_post(self, tenant_id: str, post_id: str) -> Dict:
        """Publish a GBP post via the API."""
        result = await self.db.execute(
            select(GBPPost).where(GBPPost.id == post_id, GBPPost.tenant_id == tenant_id)
        )
        post = result.scalar_one_or_none()
        if not post:
            return {"success": False, "error": "Post not found"}

        # Get location for account info
        loc_result = await self.db.execute(
            select(GBPLocation).where(GBPLocation.id == post.location_id)
        )
        location = loc_result.scalar_one_or_none()
        if not location:
            return {"success": False, "error": "Location not found"}

        creds = await gbp_oauth_service.get_credentials(tenant_id, self.db)
        if not creds:
            return {"success": False, "error": "GBP not connected"}

        # Build API payload
        payload = {
            "languageCode": "en-US",
            "summary": post.summary,
            "callToAction": {"actionType": post.call_to_action or "LEARN_MORE"},
        }
        if post.cta_url:
            payload["callToAction"]["url"] = post.cta_url
        if post.media_url:
            payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": post.media_url}]

        # POST to GBP API
        headers = {
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        }
        api_url = f"{GBP_API_BASE}/{location.gbp_account_name}/{location.gbp_location_name}/localPosts"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, json=payload, headers=headers)

        if resp.status_code in (200, 201):
            resp_data = resp.json()
            post.gbp_post_name = resp_data.get("name")
            post.status = GBPPostStatus.PUBLISHED
            post.published_at = datetime.now(timezone.utc)
            location.last_post_at = datetime.now(timezone.utc)
            await self.db.flush()
            return {"success": True, "gbp_post_name": post.gbp_post_name}
        else:
            error_msg = resp.text[:300]
            post.status = GBPPostStatus.FAILED
            post.error_message = error_msg
            post.retry_count += 1
            await self.db.flush()
            logger.warning("GBP publish failed", status=resp.status_code, error=error_msg)
            return {"success": False, "error": error_msg}

    # ── Schedule Post ───────────────────────────────────────────────

    async def schedule_post(self, tenant_id: str, post_id: str, scheduled_time: datetime) -> Dict:
        """Mark a post as scheduled for future publishing."""
        result = await self.db.execute(
            select(GBPPost).where(GBPPost.id == post_id, GBPPost.tenant_id == tenant_id)
        )
        post = result.scalar_one_or_none()
        if not post:
            return {"success": False, "error": "Post not found"}

        post.scheduled_for = scheduled_time
        post.status = GBPPostStatus.SCHEDULED
        await self.db.flush()
        return {"success": True, "scheduled_for": scheduled_time.isoformat()}

    # ── AI Auto-Generate from Campaign ──────────────────────────────

    async def auto_generate_from_campaign(
        self,
        tenant_id: str,
        location_id: str,
        service: str,
        keywords: List[str],
        headlines: List[str],
        offers: List[str],
        business_name: str = "",
        phone: str = "",
        city: str = "",
    ) -> List[GBPPost]:
        """
        AI-generate GBP posts from campaign data.
        Creates 3 posts: Update, Offer, and Seasonal/Event.
        """
        import openai

        loc_result = await self.db.execute(
            select(GBPLocation).where(GBPLocation.id == location_id)
        )
        location = loc_result.scalar_one_or_none()
        loc_city = city or (location.city if location else "")
        biz = business_name or (location.business_name if location else "")

        prompt = f"""Generate 3 Google Business Profile posts for this local business.

BUSINESS: {biz}
SERVICE: {service}
CITY: {loc_city}
PHONE: {phone}
KEYWORDS: {json.dumps(keywords[:10])}
HEADLINES: {json.dumps(headlines[:5])}
OFFERS: {json.dumps(offers[:3])}

For each post:
- 90-300 characters (optimal for GBP)
- Include city name naturally
- Include a call to action
- Use 1-2 relevant emojis
- Mention the service and business name

Return JSON:
{{
  "posts": [
    {{
      "type": "UPDATE",
      "content": "...",
      "cta": "CALL"
    }},
    {{
      "type": "OFFER",
      "content": "...",
      "cta": "LEARN_MORE"
    }},
    {{
      "type": "UPDATE",
      "content": "...",
      "cta": "BOOK"
    }}
  ]
}}"""

        try:
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a local SEO expert. Generate engaging GBP posts optimized for local search visibility."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
            )
            data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.error("GBP post AI generation failed", error=str(e))
            return []

        created = []
        for p in data.get("posts", [])[:3]:
            content = p.get("content", "")
            if not content:
                continue
            post = GBPPost(
                tenant_id=tenant_id,
                location_id=location_id,
                post_type=GBPPostType[p.get("type", "UPDATE").upper()],
                summary=content[:MAX_POST_LENGTH],
                call_to_action=p.get("cta", "LEARN_MORE"),
                cta_url=location.website if location else None,
                city_mentions=[loc_city] if loc_city else [],
                service_keywords=keywords[:5],
                status=GBPPostStatus.DRAFT,
                auto_generated=True,
                generation_model=settings.OPENAI_MODEL,
                source_campaign_id=None,
            )
            self.db.add(post)
            created.append(post)

        await self.db.flush()
        logger.info("GBP posts auto-generated", tenant_id=tenant_id, count=len(created))
        return created

    # ── List Posts ──────────────────────────────────────────────────

    async def list_posts(
        self, tenant_id: str, location_id: Optional[str] = None, limit: int = 50
    ) -> List[GBPPost]:
        """List GBP posts for tenant, optionally filtered by location."""
        q = select(GBPPost).where(GBPPost.tenant_id == tenant_id)
        if location_id:
            q = q.where(GBPPost.location_id == location_id)
        q = q.order_by(GBPPost.created_at.desc()).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    # ── Delete Post ─────────────────────────────────────────────────

    async def delete_post(self, tenant_id: str, post_id: str) -> bool:
        """Delete a draft post."""
        result = await self.db.execute(
            select(GBPPost).where(GBPPost.id == post_id, GBPPost.tenant_id == tenant_id)
        )
        post = result.scalar_one_or_none()
        if not post:
            return False
        if post.status == GBPPostStatus.PUBLISHED:
            return False  # Can't delete published posts from our DB
        await self.db.delete(post)
        await self.db.flush()
        return True

    # ── UTM Helper ──────────────────────────────────────────────────

    @staticmethod
    def add_utm_params(url: str, source: str = "gbp", campaign: str = "auto_post") -> str:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}utm_source={source}&utm_medium=social&utm_campaign={campaign}"
