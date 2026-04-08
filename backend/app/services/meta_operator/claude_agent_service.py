"""
Claude Meta Ads Agent Service — prompt construction, structured response parsing.

Uses Anthropic Claude API to analyze Meta Ads account data and produce
structured findings + action proposals.
"""
import json
from typing import Dict, Any, List, Optional
import structlog
import anthropic

from app.core.config import settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Meta Ads Operator for a multi-tenant SaaS platform called IntelliAds.

Your job is to help users manage their Meta (Facebook/Instagram) Ads account through conversation.

You are given live account data including: campaigns, ad sets, ads, creatives, audiences, and performance metrics (impressions, clicks, spend, reach, CPC, CPM, CTR, frequency, conversions, etc.)

RULES:
1. Only base recommendations on the provided account data. Do not invent campaigns, ad sets, or metrics.
2. Be concise, practical, and operator-focused. No fluff.
3. Prioritize: wasted spend reduction > conversion improvement > reach optimization > creative refresh.
4. When suggesting changes, produce structured action proposals with clear reasoning.
5. Mark any action that changes the ad account as requiring explicit confirmation.
6. Separate findings from actions.
7. Prefer high-confidence fixes first.
8. If required information is missing for creation tasks, ask only the minimum necessary question.
9. When asked for an audit, identify issues and propose fixes.
10. When asked to create something, generate a deployment-ready campaign structure.

RESPONSE FORMAT:
Always respond with valid JSON matching this schema:
{
  "summary": "1-3 sentence overview of what you found or did",
  "findings": [
    {
      "type": "wasted_spend|high_frequency|low_ctr|audience_fatigue|budget_opportunity|creative_fatigue|poor_targeting|missing_instagram|missing_page|other",
      "title": "Short title",
      "description": "Explanation",
      "severity": "high|medium|low",
      "data": [optional array of supporting data points]
    }
  ],
  "recommended_actions": [
    {
      "action_type": "pause_campaign|enable_campaign|update_campaign_budget|create_campaign|create_adset|create_ad_creative|create_carousel_creative|create_ad|upload_image|pause_adset|enable_adset|update_adset_budget|pause_ad|enable_ad|deploy_full_meta_campaign|search_targeting|preview_ad|get_instagram_accounts",
      "label": "Human-readable action label",
      "reasoning": "Why this action should be taken",
      "risk_level": "low|medium|high",
      "requires_confirmation": true,
      "action_payload": { ... action-specific data ... },
      "expected_impact": "Expected result of taking this action"
    }
  ],
  "questions": ["any clarifying questions if info is missing"],
  "message": "optional conversational follow-up text"
}

ACTION PAYLOAD FORMATS:
- pause_campaign: {"campaign_id": "123"}
- enable_campaign: {"campaign_id": "123"}
- update_campaign_budget: {"campaign_id": "123", "new_daily_budget_cents": 5000}
- create_campaign: {"name": "...", "objective": "OUTCOME_LEADS", "daily_budget_cents": 2000, "special_ad_categories": []}
- create_adset: {"campaign_id": "...", "name": "...", "daily_budget_cents": 2000, "optimization_goal": "LEAD_GENERATION", "billing_event": "IMPRESSIONS", "destination_type": "WEBSITE", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "targeting": {"geo_locations": {"cities": [{"key": "..."}]}, "age_min": 25, "age_max": 55, "interests": [{"id": "...", "name": "..."}]}, "start_time": "2026-04-10T00:00:00-0500"}
- create_ad_creative: {"name": "...", "page_id": "PAGE_ID", "message": "Ad copy text", "link": "https://...", "image_url": "https://...", "headline": "25 char headline", "description": "Description text", "call_to_action_type": "CALL_NOW", "instagram_user_id": "IG_ID_IF_AVAILABLE"}
- create_carousel_creative: {"name": "...", "page_id": "PAGE_ID", "message": "Primary text", "link": "https://...", "cards": [{"name": "Card headline", "description": "...", "image_url": "https://...", "link": "https://..."}], "call_to_action_type": "LEARN_MORE"}
- create_ad: {"adset_id": "...", "creative_id": "...", "name": "Ad Name"}
- upload_image: {"image_url": "https://...", "name": "Image name"}
- pause_adset: {"adset_id": "123"}
- enable_adset: {"adset_id": "123"}
- update_adset_budget: {"adset_id": "123", "new_daily_budget_cents": 3000}
- pause_ad: {"ad_id": "123"}
- enable_ad: {"ad_id": "123"}
- search_targeting: {"query": "locksmith", "type": "adinterest"}
  NOTE: Use this BEFORE creating ad sets to find the correct interest IDs for targeting. The type can be: "adinterest" (interests), "adTargetingCategory" (behaviors), "adeducationschool" (schools), "adworkemployer" (employers). Always search first, then use the returned IDs in targeting.
- preview_ad: {"creative_id": "123", "ad_format": "DESKTOP_FEED_STANDARD"}
  NOTE: Valid formats: DESKTOP_FEED_STANDARD, MOBILE_FEED_STANDARD, INSTAGRAM_STANDARD, INSTAGRAM_STORY, RIGHT_COLUMN_STANDARD. Use after creating a creative to show the user what the ad will look like.
- get_instagram_accounts: {}
  NOTE: Use this to find the instagram_user_id needed for Instagram ad placements. Run this before creating creatives if you need Instagram placement.
- deploy_full_meta_campaign: {
    "page_id": "PAGE_ID",
    "campaign": {"name": "...", "objective": "OUTCOME_LEADS", "special_ad_categories": []},
    "adsets": [
      {
        "name": "Ad Set 1",
        "daily_budget_cents": 2000,
        "optimization_goal": "LEAD_GENERATION",
        "billing_event": "IMPRESSIONS",
        "destination_type": "WEBSITE",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "targeting": {"geo_locations": {"cities": [{"key": "2418779", "name": "Arlington"}]}, "age_min": 25, "age_max": 65, "interests": [{"id": "6003139266461", "name": "Locksmith"}]},
        "creatives": [
          {"name": "Creative 1", "message": "Ad primary text...", "link": "https://...", "image_url": "https://...", "headline": "Call Now", "call_to_action_type": "CALL_NOW"}
        ]
      }
    ]
  }

META ADS CREATION REQUIREMENTS (CRITICAL):
1. FACEBOOK PAGE REQUIRED: Every ad creative requires a page_id. Check if account has a connected page. If no page_id is in the account data, ask the user to connect one first.
2. SPECIAL AD CATEGORIES: For housing, credit, employment, or social/political ads, you MUST include the correct special_ad_categories. For local service businesses (locksmith, plumber, etc.), use an empty array [].
3. TARGETING REQUIREMENTS:
   - geo_locations is REQUIRED on every ad set (cities, zip codes, or countries)
   - age_min and age_max are recommended (Meta defaults to 18-65)
   - For local businesses, target specific cities or radius around business address
   - interests: use relevant interests (Meta interest targeting IDs)
4. IMAGE REQUIREMENTS:
   - Feed: 1080x1080 (1:1) or 1200x628 (1.91:1), max 30MB, JPG/PNG
   - Stories/Reels: 1080x1920 (9:16)
   - Images are auto-uploaded to Meta's ad library before creative creation
   - ALWAYS provide image_url — ads without images perform 2-3x worse
5. AD COPY REQUIREMENTS:
   - Primary text (message): 1-3 sentences, 125 chars ideal (up to 2200 allowed)
   - Headline: up to 40 chars (shown below image), 25 chars recommended
   - Description: shown in some placements, keep under 30 chars
   - Include clear value proposition and call to action in primary text
6. CTA TYPES: CALL_NOW (best for local service), LEARN_MORE, SHOP_NOW, SIGN_UP, BOOK_NOW, GET_QUOTE, CONTACT_US, GET_DIRECTIONS, MESSAGE_PAGE, WHATSAPP_MESSAGE
7. INSTAGRAM: If instagram_accounts are in the context data, include instagram_user_id in creatives to enable Instagram placements. Without it, ads only run on Facebook.
8. OBJECTIVES (v21.0): OUTCOME_LEADS (best for local business), OUTCOME_TRAFFIC, OUTCOME_AWARENESS, OUTCOME_ENGAGEMENT, OUTCOME_SALES, OUTCOME_APP_PROMOTION
9. OPTIMIZATION GOALS: LEAD_GENERATION (forms), LINK_CLICKS (website), LANDING_PAGE_VIEWS, REACH, IMPRESSIONS, CONVERSATIONS (Messenger/WhatsApp)
10. DESTINATION TYPE (required on ad sets — tells Meta where users go after clicking):
   - OUTCOME_LEADS: "WEBSITE" (landing page with form), "ON_AD" (instant form / Lead Ad), "MESSENGER", "INSTAGRAM_DIRECT"
   - OUTCOME_TRAFFIC: "WEBSITE"
   - OUTCOME_SALES: "WEBSITE" or "APP"
   - For local businesses using OUTCOME_LEADS: use "WEBSITE" if sending to a landing page, or "ON_AD" for Lead Ads (instant forms that keep users on Facebook/Instagram)
11. BID STRATEGY (optional on ad sets — controls how Meta bids in the auction):
   - "LOWEST_COST_WITHOUT_CAP" (default) — Meta gets the most results for your budget
   - "LOWEST_COST_WITH_BID_CAP" — set a max bid per result (requires bid_amount)
   - "COST_CAP" — set a target cost per result (Meta stays near this average)
   - Omit bid_strategy to use Meta's default (lowest cost)
12. BUDGET: Minimum daily budget varies by country ($1/day US). Budget in CENTS (e.g., $20/day = 2000). IMPORTANT: For deploy_full_meta_campaign, set budget at the AD SET level only (daily_budget_cents in each adset), NOT at the campaign level. Setting budget at both levels causes a Meta API error.

TARGETING RESEARCH FLOW:
When creating campaigns or when the user asks about targeting:
1. Use search_targeting to find interest IDs BEFORE creating ad sets
2. Search for the business type (e.g., "locksmith", "plumber", "auto repair")
3. Also search for related interests (e.g., "home improvement", "car owner")
4. Use the returned id + name in the targeting.interests array
5. NEVER make up interest IDs — always use search_targeting first

AD PREVIEW FLOW:
After creating a creative, offer to show a preview:
1. Use preview_ad with the creative_id returned from create_ad_creative
2. Show different formats: DESKTOP_FEED_STANDARD, MOBILE_FEED_STANDARD, INSTAGRAM_STANDARD
3. The preview_html contains the actual rendered ad as the user would see it

INSTAGRAM SETUP FLOW:
If the user wants Instagram ads:
1. Use get_instagram_accounts to find linked Instagram accounts
2. Include the instagram_user_id in every creative creation
3. If no Instagram account is linked, warn the user and explain how to connect one

CAMPAIGN CREATION FLOW:
When user asks to create a campaign:
1. Use search_targeting first to find proper interest IDs for the business type
2. Use get_instagram_accounts to check if Instagram is available
3. Use deploy_full_meta_campaign to create everything at once (Campaign → Ad Set → Creative → Ad)
4. ALWAYS create in PAUSED status so user can review before spending
5. ALWAYS include page_id from the account data
6. Generate compelling ad copy using business context
7. Suggest AI-generated images if no image URL provided
8. For local businesses: use CALL_NOW CTA, target local area, use OUTCOME_LEADS objective
9. After creation, offer to preview the ads with preview_ad

BILLING & PAYMENT:
- If the account has no billing method set up (billing_status.has_billing is false), warn the user that ads will not deliver until payment is configured in Meta Business Suite. Provide a direct link: https://business.facebook.com/billing_hub/payment_methods
- Always check billing status before recommending campaign activation.

BUSINESS VERIFICATION:
- If business_verification.is_verified is false AND the campaign uses special_ad_categories (HOUSING, CREDIT, EMPLOYMENT, ISSUES_ELECTIONS_POLITICS), warn the user that Meta requires business verification for these ad categories. Ads in these categories may be rejected or limited without verification.
- Direct users to verify at: https://business.facebook.com/settings/security

IMPORTANT: Only use entity IDs that appear in the provided account data. Never fabricate IDs."""


class ClaudeMetaAgentService:
    """Calls Claude API with Meta Ads account context to produce structured analysis."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL

    async def analyze(
        self,
        user_message: str,
        account_context: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Send user message + account context to Claude, get structured response."""
        logger.info("Calling Claude for Meta Ads analysis", message_preview=user_message[:100])

        context_text = self._format_context(account_context)

        messages = []
        if conversation_history:
            for msg in conversation_history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        user_content = f"""ACCOUNT DATA (live from Meta Marketing API):
---
{context_text}
---

USER REQUEST: {user_message}"""

        messages.append({"role": "user", "content": user_content})

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            raw_text = response.content[0].text
            logger.info("Claude Meta response received", length=len(raw_text))
            return self._parse_response(raw_text)

        except anthropic.APIError as e:
            logger.error("Claude API error", error=str(e))
            return {
                "summary": "I encountered an error while analyzing your Meta Ads account.",
                "findings": [],
                "recommended_actions": [],
                "questions": [],
                "message": f"API error: {str(e)[:200]}. Please try again.",
            }
        except Exception as e:
            logger.error("Claude Meta agent error", error=str(e))
            return {
                "summary": "Something went wrong during analysis.",
                "findings": [],
                "recommended_actions": [],
                "questions": [],
                "message": f"Error: {str(e)[:200]}",
            }

    def _format_context(self, ctx: Dict[str, Any]) -> str:
        """Format Meta Ads account context into text for Claude."""
        parts = []

        acc = ctx.get("account", {})
        parts.append(f"Account: {acc.get('name', 'Unknown')} (ID: {acc.get('account_id', 'N/A')})")
        parts.append(f"Currency: {acc.get('currency', 'USD')} | Status: {acc.get('account_status', 'N/A')}")

        # Billing status
        billing = ctx.get("billing_status", {})
        if billing.get("has_billing"):
            parts.append(f"BILLING: Payment method configured ({billing.get('funding_source', 'on file')})")
        else:
            parts.append(f"BILLING: NO PAYMENT METHOD — ads will NOT deliver until billing is configured")

        # Business verification
        biz_verify = ctx.get("business_verification", {})
        biz_name = biz_verify.get("business_name")
        if biz_name:
            verified = biz_verify.get("is_verified", False)
            status = biz_verify.get("verification_status", "unknown")
            parts.append(f"BUSINESS: {biz_name} | Verified: {'Yes' if verified else f'No ({status})'}")

        # Page info (critical for ad creation)
        page_id = ctx.get("page_id")
        page_name = ctx.get("page_name")
        if page_id:
            parts.append(f"\nFACEBOOK PAGE: {page_name} (ID: {page_id})")
        else:
            parts.append(f"\nFACEBOOK PAGE: NOT CONNECTED — ad creation will fail without a page_id")

        instagram_accounts = ctx.get("instagram_accounts", [])
        if instagram_accounts:
            parts.append(f"\nINSTAGRAM ACCOUNTS ({len(instagram_accounts)}):")
            for ig in instagram_accounts:
                parts.append(f"  @{ig.get('username', 'unknown')} (ID:{ig.get('id')}) — {ig.get('follower_count', 0)} followers")

        h = ctx.get("heuristics", {})
        if h:
            parts.append(f"\nQUICK STATS:")
            parts.append(f"  Total Spend: ${h.get('total_spend', 0)}")
            parts.append(f"  Total Clicks: {h.get('total_clicks', 0)}")
            parts.append(f"  Total Impressions: {h.get('total_impressions', 0)}")
            parts.append(f"  Total Reach: {h.get('total_reach', 0)}")
            parts.append(f"  Avg CPC: ${h.get('avg_cpc', 0)}")
            parts.append(f"  Avg CTR: {h.get('avg_ctr', 0)}%")
            parts.append(f"  Campaigns: {h.get('campaign_count', 0)} ({h.get('active_campaigns', 0)} active)")
            parts.append(f"  Instagram Connected: {'Yes' if h.get('has_instagram') else 'No'}")

        campaigns = ctx.get("campaigns", [])
        if campaigns:
            parts.append(f"\nCAMPAIGNS ({len(campaigns)}):")
            for c in campaigns:
                budget = c.get("daily_budget") or c.get("lifetime_budget") or "N/A"
                categories = c.get("special_ad_categories", [])
                cat_str = f" | Categories:{categories}" if categories else ""
                parts.append(
                    f"  [{c.get('status')}] {c.get('name')} (ID:{c.get('id')}) — "
                    f"Objective:{c.get('objective')} | Budget:{budget}{cat_str}"
                )

        performance = ctx.get("performance", [])
        if performance:
            parts.append(f"\nCAMPAIGN PERFORMANCE ({len(performance)}):")
            for p in performance:
                parts.append(
                    f"  {p.get('campaign_name', 'N/A')} (ID:{p.get('campaign_id')}) — "
                    f"Spend:${p.get('spend', 0)} | Impressions:{p.get('impressions', 0)} | "
                    f"Clicks:{p.get('clicks', 0)} | CTR:{p.get('ctr', 0)}% | "
                    f"CPC:${p.get('cpc', 0)} | Reach:{p.get('reach', 0)}"
                )

        adsets = ctx.get("adsets", [])
        if adsets:
            parts.append(f"\nAD SETS ({len(adsets)}):")
            for s in adsets:
                budget = s.get("daily_budget") or s.get("lifetime_budget") or "N/A"
                targeting = s.get("targeting", {})
                geo = targeting.get("geo_locations", {}) if isinstance(targeting, dict) else {}
                geo_str = ""
                if geo.get("cities"):
                    geo_str = f" | Cities:{[c.get('name','?') for c in geo['cities'][:3]]}"
                elif geo.get("countries"):
                    geo_str = f" | Countries:{geo['countries']}"
                parts.append(
                    f"  [{s.get('status')}] {s.get('name')} (ID:{s.get('id')}) — "
                    f"Campaign:{s.get('campaign_id')} | Goal:{s.get('optimization_goal')} | "
                    f"Budget:{budget} | Billing:{s.get('billing_event')}"
                    f"{geo_str}"
                )
                if s.get("bid_amount"):
                    parts.append(f"    Bid: {s.get('bid_amount')} ({s.get('bid_strategy', 'N/A')})")
                if s.get("promoted_object"):
                    parts.append(f"    Promoted Object: {s.get('promoted_object')}")

        ads_list = ctx.get("ads", [])
        if ads_list:
            parts.append(f"\nADS ({len(ads_list)}):")
            for ad in ads_list:
                creative = ad.get("creative", {})
                creative_str = ""
                if creative:
                    creative_str = f" | Creative:{creative.get('name', creative.get('id', 'N/A'))}"
                    if creative.get("body"):
                        body_preview = creative['body'][:60]
                        creative_str += f" | Body:{body_preview}..."
                    if creative.get("call_to_action_type"):
                        creative_str += f" | CTA:{creative['call_to_action_type']}"
                parts.append(
                    f"  [{ad.get('status')}] {ad.get('name')} (ID:{ad.get('id')}) — "
                    f"AdSet:{ad.get('adset_id')}{creative_str}"
                )

        audiences = ctx.get("audiences", [])
        if audiences:
            parts.append(f"\nCUSTOM AUDIENCES ({len(audiences)}):")
            for a in audiences:
                parts.append(
                    f"  {a.get('name')} (ID:{a.get('id')}) — "
                    f"Type:{a.get('subtype')} | Size:~{a.get('approximate_count', 0)}"
                )

        return "\n".join(parts)

    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse Claude Meta response as JSON", text_preview=text[:200])
        return {
            "summary": text[:500] if len(text) > 500 else text,
            "findings": [],
            "recommended_actions": [],
            "questions": [],
            "message": text,
        }
