"""
Landing Page Agent — orchestrates the full landing page lifecycle within the
campaign creation chat flow.

Responsibilities:
1. CHECK: Does the business already have a suitable landing page for this service?
2. GENERATE: If not, create one using the existing LandingPageGenerator pipeline
3. PREVIEW: Render HTML preview for the user to review in chat
4. EDIT: Handle prompt-based edits ("change the headline", "add testimonials")
5. APPROVE: Lock in the page and link it to the campaign spec
6. IMAGES: Auto-generate hero images and section images using SEOpix

This agent is called by the campaign pipeline between Ad Copy and QA agents.
It can also be invoked standalone from the operator chat.

Flow in chat:
  Pipeline: "I notice you don't have a landing page for BMW Key Programming.
            Would you like me to create one? [Yes] [Use existing URL]"
  User: "Yes"
  Agent: Generates 3 variants → renders preview → "Here are 3 options: A (Emergency),
         B (Savings), C (Expert). Which do you prefer? Or say 'edit A: change headline to...'"
  User: "edit A: make it more urgent, add 24/7 badge"
  Agent: Applies edit → re-renders → "Updated! Here's the new version. Approve?"
  User: "approve A"
  Agent: Links landing page URL to campaign ad groups → continues pipeline
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.business_profile import BusinessProfile
from app.models.landing_page import LandingPage, LandingPageVariant
from app.models.operator import OperatorMessage

logger = structlog.get_logger()


class LandingPageAgent:
    """Orchestrates landing page creation/editing within the campaign chat flow."""

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── PUBLIC: Full flow for campaign pipeline ────────────────────

    async def run_for_campaign(
        self,
        services: List[str],
        locations: List[str],
        campaign_keywords: Dict[str, List[str]],
        campaign_headlines: Dict[str, List[str]],
        conversation_id: str,
        business_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Check/create landing pages for each service in the campaign.
        Called by the pipeline between Ad Copy and QA agents.

        Returns:
        {
            "pages": [
                {
                    "service": "BMW Key Programming",
                    "landing_page_id": "...",
                    "url": "...",
                    "status": "existing" | "generated" | "needs_approval",
                    "variants": [...],
                    "preview_html": "...",
                }
            ],
            "all_have_pages": True/False,
            "summary": "..."
        }
        """
        results = []

        for service in services:
            # Check if landing page already exists for this service
            existing = await self._find_existing_page(service)

            if existing:
                results.append({
                    "service": service,
                    "landing_page_id": existing.id,
                    "url": existing.url or f"/lp/{existing.slug}",
                    "status": "existing",
                    "audit_score": existing.audit_score,
                    "name": existing.name,
                })
                await self._emit_progress(
                    conversation_id,
                    f"Landing page for '{service}' already exists: {existing.name} "
                    f"(score: {existing.audit_score or 'unaudited'})",
                    "landing_page_check",
                )
                continue

            # Generate a new landing page
            await self._emit_progress(
                conversation_id,
                f"No landing page found for '{service}'. Generating 3 variants "
                f"(Emergency, Savings, Expert)...",
                "landing_page_generating",
            )

            svc_keywords = campaign_keywords.get(service, [])
            svc_headlines = campaign_headlines.get(service, [])
            location = locations[0] if locations else ""

            page_result = await self._generate_page(
                service=service,
                location=location,
                keywords=svc_keywords,
                headlines=svc_headlines,
                business_context=business_context,
            )

            if page_result.get("error"):
                results.append({
                    "service": service,
                    "status": "failed",
                    "error": page_result["error"],
                })
                await self._emit_progress(
                    conversation_id,
                    f"Failed to generate landing page for '{service}': {page_result['error']}",
                    "landing_page_error",
                )
                continue

            # Generate HTML preview for each variant
            variants_with_preview = []
            for variant in page_result.get("variants", []):
                preview_html = self._render_preview_html(
                    variant.get("content", {}),
                    business_context,
                    page_result.get("strategy", {}),
                )
                variants_with_preview.append({
                    **variant,
                    "preview_html": preview_html,
                })

            results.append({
                "service": service,
                "landing_page_id": page_result.get("landing_page_id"),
                "url": f"/lp/{page_result.get('slug', '')}",
                "status": "generated",
                "name": page_result.get("name"),
                "variants": variants_with_preview,
            })

            await self._emit_progress(
                conversation_id,
                f"Generated 3 landing page variants for '{service}'. "
                f"Ready for review.",
                "landing_page_ready",
                extra={
                    "type": "landing_page_preview",
                    "landing_page_id": page_result.get("landing_page_id"),
                    "service": service,
                    "variants": [
                        {
                            "id": v.get("id"),
                            "key": v.get("key"),
                            "name": v.get("name"),
                            "preview_html": v.get("preview_html", ""),
                        }
                        for v in variants_with_preview
                    ],
                },
            )

        all_ok = all(r.get("status") in ("existing", "generated") for r in results)

        return {
            "pages": results,
            "all_have_pages": all_ok,
            "summary": (
                f"Landing pages ready for {sum(1 for r in results if r.get('status') in ('existing', 'generated'))}/{len(services)} services. "
                + (f"{sum(1 for r in results if r.get('status') == 'generated')} newly generated." if any(r.get("status") == "generated" for r in results) else "All existing.")
            ),
        }

    # ── PUBLIC: Edit a variant via prompt ──────────────────────────

    async def edit_variant(
        self,
        landing_page_id: str,
        variant_key: str,
        edit_prompt: str,
        conversation_id: str,
    ) -> Dict[str, Any]:
        """
        Apply a prompt-based edit to a landing page variant.
        Called when user says "edit A: change the headline to..."
        """
        from app.services.landing_page_generator import LandingPageGenerator

        # Load the landing page and variant
        lp = await self.db.get(LandingPage, landing_page_id)
        if not lp:
            return {"error": "Landing page not found"}

        variant = None
        for v in (lp.variants or []):
            if v.variant_key == variant_key.upper():
                variant = v
                break

        if not variant:
            return {"error": f"Variant {variant_key} not found"}

        # Load business context
        biz_ctx = await self._get_business_context()

        # Apply edit
        generator = LandingPageGenerator(self.db, self.tenant_id)
        result = await generator.ai_edit_variant(
            variant_content=variant.content_json,
            edit_prompt=edit_prompt,
            strategy=lp.strategy_json,
            business_context=biz_ctx,
        )

        if result.get("error"):
            return result

        # Update variant in DB
        variant.content_json = result["content"]
        await self.db.flush()

        # Render preview
        preview_html = self._render_preview_html(
            result["content"],
            biz_ctx,
            lp.strategy_json,
        )

        await self._emit_progress(
            conversation_id,
            f"Applied edit to Variant {variant_key}: \"{edit_prompt}\". Preview updated.",
            "landing_page_edited",
            extra={
                "type": "landing_page_preview",
                "landing_page_id": landing_page_id,
                "variant_key": variant_key,
                "preview_html": preview_html,
                "edit_applied": edit_prompt,
            },
        )

        return {
            "variant_key": variant_key,
            "content": result["content"],
            "preview_html": preview_html,
            "edit_applied": edit_prompt,
        }

    # ── PUBLIC: Approve variant and link to campaign ──────────────

    async def approve_variant(
        self,
        landing_page_id: str,
        variant_key: str,
        campaign_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Approve a variant, publish the landing page, and update campaign
        ad groups to use this landing page URL.
        """
        lp = await self.db.get(LandingPage, landing_page_id)
        if not lp:
            return {"error": "Landing page not found"}

        # Mark the chosen variant as winner
        for v in (lp.variants or []):
            v.is_winner = (v.variant_key == variant_key.upper())

        # Update page status
        lp.status = "published"
        lp.published_at = datetime.now(timezone.utc)

        # Set the final URL
        page_url = lp.url or f"/lp/{lp.slug}"

        # Audit the page content
        try:
            from app.services.landing_page_auditor import LandingPageAuditor
            auditor = LandingPageAuditor(self.db, self.tenant_id)

            # Get keywords for audit
            keywords = []
            for ag in campaign_spec.get("ad_groups", []):
                if lp.service and lp.service.lower() in ag.get("name", "").lower():
                    for kw in ag.get("keywords", []):
                        text = kw.get("text", "") if isinstance(kw, dict) else str(kw)
                        keywords.append(text)

            winner_content = {}
            for v in (lp.variants or []):
                if v.variant_key == variant_key.upper():
                    winner_content = v.content_json
                    break

            audit = await auditor.audit_generated(
                content_json=winner_content,
                campaign_keywords=keywords[:10],
                campaign_headlines=[],
                service=lp.service or "",
                location=lp.location or "",
            )
            lp.audit_score = audit.get("score", 0)
            lp.audit_json = audit
            lp.last_audited_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.warning("Landing page audit failed", error=str(e))

        # Update campaign spec: set final_urls in matching ad groups
        for ag in campaign_spec.get("ad_groups", []):
            if lp.service and lp.service.lower() in ag.get("name", "").lower():
                for ad in ag.get("ads", []):
                    ad["final_url"] = page_url
                    ad["final_urls"] = [page_url]

        await self.db.flush()

        return {
            "landing_page_id": lp.id,
            "url": page_url,
            "status": "published",
            "audit_score": lp.audit_score,
            "variant_approved": variant_key,
            "ad_groups_updated": sum(
                1 for ag in campaign_spec.get("ad_groups", [])
                if lp.service and lp.service.lower() in ag.get("name", "").lower()
            ),
        }

    # ── PUBLIC: Regenerate a variant with a different angle ────────

    async def regenerate_variant(
        self,
        landing_page_id: str,
        variant_key: str,
        new_angle: str = "",
        conversation_id: str = "",
    ) -> Dict[str, Any]:
        """Regenerate a specific variant with a new or enhanced angle."""
        lp = await self.db.get(LandingPage, landing_page_id)
        if not lp:
            return {"error": "Landing page not found"}

        biz_ctx = await self._get_business_context()

        # Use ai_edit as a full regeneration with angle instruction
        from app.services.landing_page_generator import LandingPageGenerator
        generator = LandingPageGenerator(self.db, self.tenant_id)

        variant = None
        for v in (lp.variants or []):
            if v.variant_key == variant_key.upper():
                variant = v
                break
        if not variant:
            return {"error": f"Variant {variant_key} not found"}

        edit_prompt = (
            f"Completely regenerate this landing page with a {new_angle or 'fresh'} angle. "
            f"New headline, new copy, new CTAs — but keep the same business details and service. "
            f"Make it dramatically different from the current version."
        )

        result = await generator.ai_edit_variant(
            variant_content=variant.content_json,
            edit_prompt=edit_prompt,
            strategy=lp.strategy_json,
            business_context=biz_ctx,
        )

        if result.get("error"):
            return result

        variant.content_json = result["content"]
        await self.db.flush()

        preview_html = self._render_preview_html(
            result["content"], biz_ctx, lp.strategy_json,
        )

        if conversation_id:
            await self._emit_progress(
                conversation_id,
                f"Regenerated Variant {variant_key} with {new_angle or 'fresh'} angle.",
                "landing_page_regenerated",
                extra={
                    "type": "landing_page_preview",
                    "landing_page_id": landing_page_id,
                    "variant_key": variant_key,
                    "preview_html": preview_html,
                },
            )

        return {
            "variant_key": variant_key,
            "content": result["content"],
            "preview_html": preview_html,
            "angle": new_angle,
        }

    # ── PUBLIC: Generate images for a landing page ────────────────

    async def generate_images(
        self,
        landing_page_id: str,
        conversation_id: str = "",
    ) -> Dict[str, Any]:
        """Generate hero and section images for all variants using SEOpix."""
        from app.integrations.image_generator.client import ImageGeneratorClient

        lp = await self.db.get(LandingPage, landing_page_id)
        if not lp:
            return {"error": "Landing page not found"}

        img_client = ImageGeneratorClient()
        if not img_client.is_configured:
            return {"error": "Image generator not configured"}

        biz_ctx = await self._get_business_context()
        results = []

        for variant in (lp.variants or []):
            content = variant.content_json or {}
            hero = content.get("hero", {})
            prompt = hero.get("hero_image_prompt", "")

            if not prompt:
                prompt = (
                    f"Professional {biz_ctx.get('industry', 'service')} business: "
                    f"expert performing {lp.service or 'service'} work. "
                    f"Clean, modern, well-lit. Photorealistic, high quality hero image."
                )

            try:
                img_result = await img_client.generate_single(
                    prompt=prompt,
                    engine="dalle",
                    style="photorealistic",
                    size="1792x1024",
                    metadata={
                        "businessName": biz_ctx.get("name", ""),
                        "businessType": biz_ctx.get("industry", "service"),
                        "city": biz_ctx.get("city", ""),
                        "description": f"{lp.service} landing page hero",
                    },
                )
                if img_result.get("success"):
                    hero["hero_image_url"] = img_result["image_url"]
                    content["hero"] = hero
                    variant.content_json = content
                    results.append({
                        "variant_key": variant.variant_key,
                        "status": "success",
                        "image_url": img_result["image_url"],
                    })
                else:
                    results.append({
                        "variant_key": variant.variant_key,
                        "status": "failed",
                        "error": img_result.get("error", "Unknown"),
                    })
            except Exception as e:
                results.append({
                    "variant_key": variant.variant_key,
                    "status": "failed",
                    "error": str(e)[:100],
                })

        await self.db.flush()

        if conversation_id:
            success_count = sum(1 for r in results if r["status"] == "success")
            await self._emit_progress(
                conversation_id,
                f"Generated {success_count}/{len(results)} hero images for landing page variants.",
                "landing_page_images",
            )

        return {"images": results}

    # ── PRIVATE: Find existing landing page ───────────────────────

    async def _find_existing_page(self, service: str) -> Optional[LandingPage]:
        """Check if a published/draft landing page exists for this service."""
        result = await self.db.execute(
            select(LandingPage).where(
                LandingPage.tenant_id == self.tenant_id,
                LandingPage.service.ilike(f"%{service}%"),
                LandingPage.status.in_(["published", "draft", "preview"]),
            ).order_by(LandingPage.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    # ── PRIVATE: Generate landing page via existing service ───────

    async def _generate_page(
        self,
        service: str,
        location: str,
        keywords: List[str],
        headlines: List[str],
        business_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call the existing LandingPageGenerator to create a page."""
        from app.services.landing_page_generator import LandingPageGenerator

        generator = LandingPageGenerator(self.db, self.tenant_id)
        return await generator.generate(
            service=service,
            location=location,
            industry=business_context.get("industry", ""),
            business_name=business_context.get("name", ""),
            phone=business_context.get("phone", ""),
            website=business_context.get("website", ""),
            usps=business_context.get("usps", []),
            offers=business_context.get("offers", []),
            campaign_keywords=keywords,
            campaign_headlines=headlines,
            trust_signals=business_context.get("trust_signals", []),
            description=business_context.get("description", ""),
        )

    # ── PRIVATE: Get business context ─────────────────────────────

    async def _get_business_context(self) -> Dict[str, Any]:
        """Load business profile for this tenant."""
        result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == self.tenant_id)
        )
        bp = result.scalar_one_or_none()
        if not bp:
            return {}

        return {
            "name": getattr(bp, "description", "") or "",
            "business_name": getattr(bp, "description", "") or "",
            "industry": bp.industry_classification or "",
            "phone": bp.phone or "",
            "website": bp.website_url or "",
            "city": bp.city or "",
            "state": bp.state or "",
            "services": bp.services_json or [],
            "usps": bp.usp_json or [],
            "offers": bp.offers_json or [],
            "trust_signals": bp.trust_signals_json or [],
            "google_rating": bp.google_rating or 0,
            "review_count": bp.review_count or 0,
            "years_experience": bp.years_experience or 0,
        }

    # ── PRIVATE: Emit progress to conversation ────────────────────

    async def _emit_progress(
        self, conversation_id: str, detail: str, status: str,
        extra: Dict = None,
    ):
        """Insert a progress message into the operator conversation."""
        if not conversation_id:
            return

        payload = {
            "type": "landing_page_progress",
            "agent": "Landing Page",
            "status": status,
            "detail": detail,
        }
        if extra:
            payload.update(extra)

        msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=f"Landing Page: {detail}",
            structured_payload=payload,
        )
        self.db.add(msg)
        try:
            await self.db.flush()
        except Exception:
            pass

    # ── HTML PREVIEW RENDERER ─────────────────────────────────────

    def _render_preview_html(
        self,
        content: Dict[str, Any],
        business_context: Dict[str, Any],
        strategy: Dict[str, Any],
    ) -> str:
        """
        Render landing page content JSON into a complete HTML preview.
        This produces a real, styled HTML page that can be embedded in an iframe
        or displayed in the chat UI.
        """
        hero = content.get("hero", {})
        trust_bar = content.get("trust_bar", {})
        services_section = content.get("services_section", {})
        why_us = content.get("why_us_section", {})
        reviews = content.get("reviews_section", {})
        faq = content.get("faq_section", {})
        cta_footer = content.get("cta_footer", {})

        # Style from strategy
        style = strategy.get("style", {})
        primary_color = style.get("primary_color", "#1a56db")
        accent_color = style.get("accent_color", "#e02424")
        font = style.get("font_family", "Inter")

        phone = hero.get("cta_phone", business_context.get("phone", ""))
        biz_name = business_context.get("name", business_context.get("business_name", ""))

        # Build HTML sections
        hero_img = ""
        if hero.get("hero_image_url"):
            hero_img = f'<img src="{hero["hero_image_url"]}" alt="{biz_name}" style="width:100%;max-height:400px;object-fit:cover;border-radius:12px;margin-top:20px;">'

        trust_items_html = ""
        for item in trust_bar.get("items", []):
            trust_items_html += f'<span style="padding:8px 16px;background:rgba(255,255,255,0.15);border-radius:20px;font-size:14px;">{_esc(str(item))}</span>'

        services_html = ""
        for svc in services_section.get("services", []):
            icon = _icon_map(svc.get("icon", "star"))
            services_html += f'''
            <div style="background:#fff;padding:24px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);flex:1;min-width:250px;">
                <div style="font-size:28px;margin-bottom:8px;">{icon}</div>
                <h3 style="margin:0 0 8px;color:#111;">{_esc(svc.get("name", ""))}</h3>
                <p style="margin:0;color:#555;font-size:14px;line-height:1.5;">{_esc(svc.get("description", ""))}</p>
            </div>'''

        reasons_html = ""
        for reason in why_us.get("reasons", []):
            icon = _icon_map(reason.get("icon", "star"))
            reasons_html += f'''
            <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:16px;">
                <div style="font-size:24px;flex-shrink:0;">{icon}</div>
                <div>
                    <strong style="color:#111;">{_esc(reason.get("title", ""))}</strong>
                    <p style="margin:4px 0 0;color:#555;font-size:14px;">{_esc(reason.get("description", ""))}</p>
                </div>
            </div>'''

        reviews_html = ""
        for review in reviews.get("reviews", [])[:3]:
            stars = "".join(["&#9733;"] * min(review.get("rating", 5), 5))
            reviews_html += f'''
            <div style="background:#fff;padding:20px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.06);flex:1;min-width:250px;">
                <div style="color:#f59e0b;font-size:18px;margin-bottom:8px;">{stars}</div>
                <p style="color:#333;font-size:14px;line-height:1.5;margin:0 0 12px;">"{_esc(review.get("text", ""))}"</p>
                <div style="color:#888;font-size:13px;">— {_esc(review.get("name", "Customer"))}</div>
            </div>'''

        faq_html = ""
        for faq_item in faq.get("faqs", [])[:5]:
            faq_html += f'''
            <div style="border-bottom:1px solid #eee;padding:16px 0;">
                <div style="font-weight:600;color:#111;margin-bottom:8px;">{_esc(faq_item.get("question", ""))}</div>
                <div style="color:#555;font-size:14px;line-height:1.6;">{_esc(faq_item.get("answer", ""))}</div>
            </div>'''

        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family={font}:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'{font}',system-ui,sans-serif; color:#111; background:#f8f9fa; }}
  .container {{ max-width:720px; margin:0 auto; padding:0 20px; }}
  a {{ text-decoration:none; }}
</style>
</head>
<body>

<!-- HERO -->
<section style="background:linear-gradient(135deg, {primary_color}, {_darken(primary_color)});color:#fff;padding:48px 20px 40px;text-align:center;">
  <div class="container">
    {f'<div style="background:{accent_color};color:#fff;display:inline-block;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;margin-bottom:16px;">{_esc(hero.get("urgency_badge", ""))}</div>' if hero.get("urgency_badge") else ""}
    <h1 style="font-size:32px;font-weight:700;line-height:1.2;margin-bottom:12px;">{_esc(hero.get("headline", "Professional Service"))}</h1>
    <p style="font-size:18px;opacity:0.9;margin-bottom:24px;max-width:600px;margin-left:auto;margin-right:auto;">{_esc(hero.get("subheadline", ""))}</p>
    <a href="tel:{phone}" style="display:inline-block;background:{accent_color};color:#fff;padding:16px 32px;border-radius:8px;font-size:18px;font-weight:700;box-shadow:0 4px 12px rgba(0,0,0,0.3);">
      {_esc(hero.get("cta_text", "Call Now"))}
    </a>
    {hero_img}
  </div>
</section>

<!-- TRUST BAR -->
{f"""<section style="background:{_darken(primary_color)};padding:12px 20px;text-align:center;">
  <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;color:#fff;">
    {trust_items_html}
  </div>
</section>""" if trust_items_html else ""}

<!-- SERVICES -->
{f"""<section style="padding:48px 20px;background:#f8f9fa;">
  <div class="container">
    <h2 style="text-align:center;font-size:26px;margin-bottom:32px;color:#111;">{_esc(services_section.get("heading", "Our Services"))}</h2>
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
      {services_html}
    </div>
  </div>
</section>""" if services_html else ""}

<!-- WHY US -->
{f"""<section style="padding:48px 20px;background:#fff;">
  <div class="container">
    <h2 style="text-align:center;font-size:26px;margin-bottom:32px;color:#111;">{_esc(why_us.get("heading", "Why Choose Us"))}</h2>
    {reasons_html}
  </div>
</section>""" if reasons_html else ""}

<!-- REVIEWS -->
{f"""<section style="padding:48px 20px;background:#f8f9fa;">
  <div class="container">
    <h2 style="text-align:center;font-size:26px;margin-bottom:32px;color:#111;">{_esc(reviews.get("heading", "Customer Reviews"))}</h2>
    <div style="display:flex;gap:16px;flex-wrap:wrap;">
      {reviews_html}
    </div>
  </div>
</section>""" if reviews_html else ""}

<!-- FAQ -->
{f"""<section style="padding:48px 20px;background:#fff;">
  <div class="container">
    <h2 style="text-align:center;font-size:26px;margin-bottom:24px;color:#111;">{_esc(faq.get("heading", "FAQ"))}</h2>
    {faq_html}
  </div>
</section>""" if faq_html else ""}

<!-- CTA FOOTER -->
<section style="background:linear-gradient(135deg, {primary_color}, {_darken(primary_color)});color:#fff;padding:48px 20px;text-align:center;">
  <div class="container">
    <h2 style="font-size:28px;margin-bottom:12px;">{_esc(cta_footer.get("heading", "Ready to Get Started?"))}</h2>
    <p style="font-size:16px;opacity:0.9;margin-bottom:24px;">{_esc(cta_footer.get("subtext", ""))}</p>
    <a href="tel:{phone}" style="display:inline-block;background:{accent_color};color:#fff;padding:16px 32px;border-radius:8px;font-size:18px;font-weight:700;box-shadow:0 4px 12px rgba(0,0,0,0.3);">
      {_esc(cta_footer.get("cta_text", "Call Now"))}
    </a>
    <p style="margin-top:16px;font-size:14px;opacity:0.7;">{_esc(biz_name)} &bull; {phone}</p>
  </div>
</section>

</body>
</html>'''

        return html


# ── HELPER FUNCTIONS ──────────────────────────────────────────────

def _esc(text: str) -> str:
    """Basic HTML escaping."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _icon_map(icon_name: str) -> str:
    """Map icon names to emoji for HTML preview."""
    icons = {
        "key": "&#128273;",
        "shield": "&#128737;",
        "clock": "&#9200;",
        "star": "&#11088;",
        "wrench": "&#128295;",
        "phone": "&#128222;",
        "check": "&#9989;",
        "lock": "&#128274;",
        "car": "&#128663;",
        "home": "&#127968;",
        "tool": "&#128736;",
        "award": "&#127942;",
        "map": "&#128205;",
        "dollar": "&#128176;",
        "heart": "&#10084;",
        "lightning": "&#9889;",
        "thumbsup": "&#128077;",
    }
    return icons.get(icon_name.lower(), "&#11088;")


def _darken(hex_color: str) -> str:
    """Darken a hex color by ~20% for gradients."""
    try:
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        r, g, b = max(0, int(r * 0.75)), max(0, int(g * 0.75)), max(0, int(b * 0.75))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#0d2f6b"
