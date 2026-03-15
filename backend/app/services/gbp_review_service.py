"""
Google Business Profile Review Management Service.
AI-powered review responses, sentiment analysis, monitoring.
"""
import json
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import openai

from app.core.config import settings
from app.models.gbp_post import GBPReview
from app.models.gbp_location import GBPLocation
from app.models.business_profile import BusinessProfile
from app.services.gbp_service import GBPService

logger = structlog.get_logger()


class GBPReviewService:
    """AI-powered review management for GBP."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Sync Reviews from GBP ───────────────────────────────────────

    async def sync_reviews(self, tenant_id: str, location_id: str) -> Dict:
        """Fetch and sync reviews from GBP API into local DB."""
        loc_result = await self.db.execute(
            select(GBPLocation).where(
                GBPLocation.id == location_id, GBPLocation.tenant_id == tenant_id
            )
        )
        location = loc_result.scalar_one_or_none()
        if not location or not location.gbp_location_name:
            return {"success": False, "error": "Location not found or not connected to GBP"}

        gbp = GBPService(self.db)
        # Build the full location resource name for reviews API
        loc_name = location.gbp_location_name
        if location.gbp_account_name:
            full_name = f"{location.gbp_account_name}/{loc_name}"
        else:
            full_name = loc_name

        reviews_data = await gbp.fetch_reviews(tenant_id, full_name)
        count = await gbp.sync_reviews_to_db(tenant_id, location_id, reviews_data)

        # Update location metrics
        location.google_rating = reviews_data.get("averageRating")
        location.review_count = reviews_data.get("totalReviewCount", 0)
        await self.db.flush()

        return {
            "success": True,
            "synced": count,
            "average_rating": reviews_data.get("averageRating"),
            "total_reviews": reviews_data.get("totalReviewCount", 0),
        }

    # ── List Reviews ────────────────────────────────────────────────

    async def list_reviews(
        self,
        tenant_id: str,
        location_id: Optional[str] = None,
        unresponded_only: bool = False,
        limit: int = 50,
    ) -> Dict:
        """List reviews with summary stats."""
        q = select(GBPReview).where(GBPReview.tenant_id == tenant_id)
        if location_id:
            q = q.where(GBPReview.location_id == location_id)
        if unresponded_only:
            q = q.where(GBPReview.has_owner_reply == False)
        q = q.order_by(GBPReview.review_time.desc()).limit(limit)

        result = await self.db.execute(q)
        reviews = list(result.scalars().all())

        # Summary stats
        total_q = select(func.count(GBPReview.id)).where(GBPReview.tenant_id == tenant_id)
        if location_id:
            total_q = total_q.where(GBPReview.location_id == location_id)
        total_result = await self.db.execute(total_q)
        total = total_result.scalar() or 0

        unresponded_q = total_q.where(GBPReview.has_owner_reply == False)
        unresponded_result = await self.db.execute(unresponded_q)
        unresponded = unresponded_result.scalar() or 0

        avg_q = select(func.avg(GBPReview.rating)).where(GBPReview.tenant_id == tenant_id)
        if location_id:
            avg_q = avg_q.where(GBPReview.location_id == location_id)
        avg_result = await self.db.execute(avg_q)
        avg_rating = avg_result.scalar() or 0.0

        return {
            "reviews": [
                {
                    "id": r.id,
                    "reviewer_name": r.reviewer_name,
                    "rating": r.rating,
                    "comment": r.comment,
                    "review_time": r.review_time.isoformat() if r.review_time else None,
                    "has_owner_reply": r.has_owner_reply,
                    "owner_reply": r.owner_reply,
                    "ai_generated_reply": r.ai_generated_reply,
                    "ai_reply_approved": r.ai_reply_approved,
                    "sentiment": r.sentiment,
                }
                for r in reviews
            ],
            "summary": {
                "total_reviews": total,
                "average_rating": round(float(avg_rating), 2),
                "unresponded_count": unresponded,
                "response_rate": round(((total - unresponded) / total * 100) if total > 0 else 0, 1),
            },
        }

    # ── AI Generate Review Response ─────────────────────────────────

    async def generate_ai_response(
        self,
        tenant_id: str,
        review_id: str,
        tone: str = "professional",
    ) -> Dict:
        """Use AI to generate a personalized review response."""
        rev_result = await self.db.execute(
            select(GBPReview).where(
                GBPReview.id == review_id, GBPReview.tenant_id == tenant_id
            )
        )
        review = rev_result.scalar_one_or_none()
        if not review:
            return {"success": False, "error": "Review not found"}

        # Get business name
        bp_result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
        )
        bp = bp_result.scalar_one_or_none()
        biz_name = bp.description[:100] if bp and bp.description else "our business"

        # Get tenant name for business identity
        from app.models.tenant import Tenant
        t_result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = t_result.scalar_one_or_none()
        business_name = tenant.name if tenant else "our business"

        rating_context = {
            5: "extremely positive",
            4: "very positive",
            3: "neutral/mixed",
            2: "somewhat negative",
            1: "very negative",
        }

        tone_map = {
            "professional": "formal, polished, and professional",
            "friendly": "warm, approachable, and friendly",
            "casual": "relaxed, conversational, and casual",
        }

        prompt = f"""You are a review response expert for {business_name}.
Generate a {tone_map.get(tone, 'professional')} response to this {rating_context.get(review.rating, 'neutral')} review.

Review Details:
- Reviewer: {review.reviewer_name}
- Rating: {review.rating}/5 stars
- Review: "{review.comment or '(No comment)'}"

Guidelines:
- Thank the reviewer by first name if available
- For positive reviews (4-5 stars): express gratitude, reinforce what they loved, invite them back
- For neutral reviews (3 stars): acknowledge feedback, mention improvements, invite to return
- For negative reviews (1-2 stars): apologize sincerely, address concerns, offer to make it right, provide contact info
- Keep response 50-150 words
- Include the business name naturally
- Sound authentic, not robotic
- NEVER be defensive or dismissive
- End with a warm closing

Return JSON:
{{
  "response": "the review response text",
  "suggested_action": "none|follow_up|urgent"
}}"""

        try:
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert at writing review responses that build trust and encourage return business."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            data = json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.error("AI review response generation failed", error=str(e))
            return {"success": False, "error": f"AI generation failed: {str(e)}"}

        reply_text = data.get("response", "")
        review.ai_generated_reply = reply_text
        review.ai_reply_approved = False
        await self.db.flush()

        return {
            "success": True,
            "review_id": review_id,
            "ai_response": reply_text,
            "suggested_action": data.get("suggested_action", "none"),
        }

    # ── Approve & Post AI Reply ─────────────────────────────────────

    async def approve_and_post_reply(self, tenant_id: str, review_id: str) -> Dict:
        """Approve the AI-generated reply and post it to GBP."""
        rev_result = await self.db.execute(
            select(GBPReview).where(
                GBPReview.id == review_id, GBPReview.tenant_id == tenant_id
            )
        )
        review = rev_result.scalar_one_or_none()
        if not review:
            return {"success": False, "error": "Review not found"}
        if not review.ai_generated_reply:
            return {"success": False, "error": "No AI reply to approve"}

        # Post to GBP API
        gbp = GBPService(self.db)
        if review.gbp_review_name:
            posted = await gbp.reply_to_review(tenant_id, review.gbp_review_name, review.ai_generated_reply)
        else:
            posted = False

        review.ai_reply_approved = True
        review.owner_reply = review.ai_generated_reply
        review.owner_reply_time = datetime.now(timezone.utc)
        review.has_owner_reply = True
        await self.db.flush()

        return {
            "success": True,
            "posted_to_gbp": posted,
            "reply": review.owner_reply,
        }

    # ── Bulk Generate Responses ─────────────────────────────────────

    async def bulk_generate_responses(
        self, tenant_id: str, review_ids: List[str], tone: str = "professional"
    ) -> List[Dict]:
        """Generate AI responses for multiple reviews."""
        results = []
        for rid in review_ids:
            result = await self.generate_ai_response(tenant_id, rid, tone)
            results.append(result)
        return results
