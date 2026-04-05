"""
Claude Ads Agent Service — prompt construction, structured response parsing.

Uses Anthropic Claude API to analyze Google Ads account data and produce
structured findings + action proposals.
"""
import json
from typing import Dict, Any, List, Optional
import structlog
import anthropic

from app.core.config import settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Google Ads Operator for a multi-tenant SaaS platform called IgniteAds.

Your job is to help users manage their Google Ads account through conversation.

You are given live account data including: campaigns, ad groups, keywords, search terms, ads, and performance metrics (impressions, clicks, cost, conversions, CTR, CPC, etc.)

RULES:
1. Only base recommendations on the provided account data. Do not invent campaigns, keywords, or metrics.
2. Be concise, practical, and operator-focused. No fluff.
3. Prioritize: wasted spend reduction > conversion improvement > CTR improvement > campaign clarity.
4. When suggesting changes, produce structured action proposals with clear reasoning.
5. Mark any action that changes the ad account as requiring explicit confirmation.
6. Separate findings from actions.
7. Prefer high-confidence fixes first.
8. If required information is missing for creation tasks, ask only the minimum necessary question.
9. When asked for an audit, identify issues and propose fixes.
10. When asked to create something, generate a deployment-ready campaign structure.
11. When asked to apply fixes, only act on approved actions.

RESPONSE FORMAT:
Always respond with valid JSON matching this schema:
{
  "summary": "1-3 sentence overview of what you found or did",
  "findings": [
    {
      "type": "wasted_spend|low_ctr|missing_negatives|budget_opportunity|low_quality|poor_structure|other",
      "title": "Short title",
      "description": "Explanation",
      "severity": "high|medium|low",
      "data": [optional array of supporting data points]
    }
  ],
  "recommended_actions": [
    {
      "action_type": "pause_keyword|enable_keyword|update_keyword_bid|add_negative_keyword|update_campaign_budget|pause_campaign|enable_campaign|pause_ad|enable_ad|pause_ad_group|enable_ad_group|set_device_bid_modifier|add_location_targeting|set_ad_schedule|apply_recommendation|create_sitelinks|create_callouts|create_structured_snippets|create_image_asset|link_image_to_campaign|create_promotion|deploy_full_campaign|create_campaign|create_ad_group|create_responsive_search_ad|create_call_ad|add_keywords|generate_ad_image|list_google_ads_assets",
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
- pause_keyword: {"keyword_ids": ["id1", "id2"], "ad_group_id": "123"}
- enable_keyword: {"keyword_ids": ["id1", "id2"], "ad_group_id": "123"}
- update_keyword_bid: {"ad_group_id": "123", "criterion_id": "456", "new_cpc_bid": 5.00}
- add_negative_keyword: {"terms": ["term1", "term2"], "campaign_id": "123"}
- update_campaign_budget: {"campaign_id": "123", "new_daily_budget": 50.00}
- pause_campaign: {"campaign_id": "123"}
- enable_campaign: {"campaign_id": "123"}
- pause_ad: {"ad_group_id": "123", "ad_id": "456"}
- enable_ad: {"ad_group_id": "123", "ad_id": "456"}
- pause_ad_group: {"ad_group_id": "123"}
- enable_ad_group: {"ad_group_id": "123"}
- set_device_bid_modifier: {"campaign_id": "123", "device": "MOBILE|DESKTOP|TABLET", "bid_modifier": 1.2}
- add_location_targeting: {"campaign_id": "123", "location_id": "1014221"}
- set_ad_schedule: {"campaign_id": "123", "day_of_week": "MONDAY", "start_hour": 8, "end_hour": 20, "bid_modifier": 1.0}
- apply_recommendation: {"resource_name": "customers/123/recommendations/456"}
- create_sitelinks: {"campaign_id": "123", "sitelinks": [{"link_text": "About Us", "final_url": "https://...", "description1": "Learn more", "description2": "About our services"}]}
- create_callouts: {"campaign_id": "123", "callouts": ["Free Estimates", "24/7 Service", "Licensed & Insured"]}
- create_structured_snippets: {"campaign_id": "123", "header": "Services", "values": ["Car Locksmith", "Key Programming", "ECU Repair"]}
- create_image_asset: {"image_url": "https://...", "asset_name": "Hero Image"}
- link_image_to_campaign: {"campaign_id": "123", "asset_resource": "customers/123/assets/456"}
- create_promotion: {"campaign_id": "123", "promotion_target": "Key Service", "percent_off": 15, "final_url": "https://..."}
- deploy_full_campaign: {"campaign": {"name": "descriptive campaign name"}, "services": ["Service 1", "Service 2"], "locations": ["City 1"], "intent": "brief description of what the user wants"}
  NOTE: For deploy_full_campaign, only provide the campaign name, target services, locations, and user intent. A specialized multi-agent pipeline will handle keyword research, ad copy, targeting, extensions, and QA automatically. Do NOT try to generate full ad groups, keywords, headlines, or descriptions — the pipeline produces expert-quality output for all of those.
- create_campaign: {"name": "...", "budget_micros": 30000000}
- create_ad_group: {"campaign_resource": "...", "name": "...", "cpc_bid_micros": 5000000}
- create_responsive_search_ad: {"ad_group_resource": "...", "headlines": [...], "descriptions": [...], "final_url": "..."}
- create_call_ad: {"ad_group_resource": "...", "business_name": "...", "phone_number": "...", "headline1": "...", "headline2": "...", "description1": "...", "description2": "...", "final_url": "..."}
- add_keywords: {"ad_group_resource": "...", "keywords": [{"text": "...", "match_type": "PHRASE"}]}
- generate_ad_image: {"prompt": "descriptive image prompt", "engine": "dalle|stability|flux|google", "style": "photorealistic|cartoon|artistic", "size": "1024x1024|1792x1024|1024x1792", "upload_to_google": true, "campaign_id": "123", "asset_name": "My Ad Image"}
- list_google_ads_assets: {"asset_types": ["IMAGE", "SITELINK", "CALLOUT", "STRUCTURED_SNIPPET", "PROMOTION"]}

IMAGE GENERATION NOTES:
- Use generate_ad_image when the user asks to create images for ads. Write a detailed, professional prompt.
- Common sizes: 1024x1024 (square, display ads), 1792x1024 (landscape, banners), 1024x1792 (portrait, stories)
- Set upload_to_google=true and provide campaign_id to auto-attach the image to a campaign.
- Use list_google_ads_assets first to check what images already exist before generating new ones.
- Engines: dalle (best quality), stability (fastest), flux (most artistic control), google (Google Gemini — clean marketing visuals).

IMPORTANT: Only use entity IDs that appear in the provided account data. Never fabricate IDs."""


class ClaudeAdsAgentService:
    """Calls Claude API with account context to produce structured analysis."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL

    async def analyze(
        self,
        user_message: str,
        account_context: Dict[str, Any],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Send user message + account context to Claude, get structured response."""
        logger.info("Calling Claude for analysis", message_preview=user_message[:100])

        # Build context summary for Claude
        context_text = self._format_context(account_context)

        # Build messages
        messages = []

        # Include conversation history (last 10 turns max)
        if conversation_history:
            for msg in conversation_history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Current user message with context
        user_content = f"""ACCOUNT DATA (live from Google Ads API):
---
{context_text}
---

USER REQUEST: {user_message}"""

        messages.append({"role": "user", "content": user_content})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
            )

            raw_text = response.content[0].text
            logger.info("Claude response received", length=len(raw_text))

            # Parse JSON from response
            parsed = self._parse_response(raw_text)
            return parsed

        except anthropic.APIError as e:
            logger.error("Claude API error", error=str(e))
            return {
                "summary": "I encountered an error while analyzing your account.",
                "findings": [],
                "recommended_actions": [],
                "questions": [],
                "message": f"API error: {str(e)[:200]}. Please try again.",
            }
        except Exception as e:
            logger.error("Claude agent error", error=str(e))
            return {
                "summary": "Something went wrong during analysis.",
                "findings": [],
                "recommended_actions": [],
                "questions": [],
                "message": f"Error: {str(e)[:200]}",
            }

    def _format_context(self, ctx: Dict[str, Any]) -> str:
        """Format account context into a concise text block for Claude."""
        parts = []

        # Account info
        acc = ctx.get("account", {})
        parts.append(f"Account: {acc.get('name', 'Unknown')} (ID: {acc.get('customer_id', 'N/A')})")
        parts.append(f"Date Range: {ctx.get('date_range', 'LAST_30_DAYS')}")

        # Heuristics summary
        h = ctx.get("heuristics", {})
        if h:
            parts.append(f"\nQUICK STATS:")
            parts.append(f"  Keywords with spend + 0 conversions: {h.get('wasted_keyword_count', 0)} (${h.get('wasted_keyword_spend', 0)})")
            parts.append(f"  Low CTR ads (<2%): {h.get('low_ctr_ad_count', 0)}")
            parts.append(f"  Search terms to negate: {h.get('negative_keyword_opportunities', 0)} (${h.get('negative_keyword_wasted_spend', 0)})")

        # Campaign performance
        campaigns = ctx.get("campaign_performance", [])
        if campaigns:
            parts.append(f"\nCAMPAIGNS ({len(campaigns)}):")
            for c in campaigns:
                parts.append(
                    f"  [{c['status']}] {c['name']} (ID:{c['campaign_id']}) — "
                    f"Budget:${c['daily_budget']}/day | Cost:${c['cost']} | "
                    f"Clicks:{c['clicks']} | CTR:{c['ctr']}% | "
                    f"Conv:{c['conversions']} | CPA:${c['cost_per_conversion']}"
                )

        # Top keywords by spend
        keywords = ctx.get("keyword_performance", [])
        if keywords:
            parts.append(f"\nTOP KEYWORDS BY SPEND ({len(keywords)}):")
            for k in keywords[:30]:
                qs = f" QS:{k['quality_score']}" if k.get("quality_score") else ""
                parts.append(
                    f"  [{k['match_type']}] \"{k['text']}\" (ID:{k['keyword_id']}, AG:{k['ad_group_id']}) — "
                    f"${k['cost']} | {k['clicks']}cl | CTR:{k['ctr']}% | Conv:{k['conversions']}{qs}"
                )

        # Search terms
        search_terms = ctx.get("search_terms", [])
        if search_terms:
            parts.append(f"\nSEARCH TERMS ({len(search_terms)}):")
            for t in search_terms[:40]:
                parts.append(
                    f"  \"{t['search_term']}\" — ${t['cost']} | {t['clicks']}cl | Conv:{t['conversions']} | Camp:{t['campaign_id']}"
                )

        # Ad performance
        ads = ctx.get("ad_performance", [])
        if ads:
            parts.append(f"\nADS ({len(ads)}):")
            for a in ads[:15]:
                strength = f" Strength:{a['ad_strength']}" if a.get("ad_strength") else ""
                parts.append(
                    f"  AD {a['ad_id']} ({a['ad_group_name']}) — "
                    f"${a['cost']} | {a['clicks']}cl | CTR:{a['ctr']}% | Conv:{a['conversions']}{strength}"
                )

        # Conversion tracking
        conv_actions = ctx.get("conversion_actions", [])
        if conv_actions:
            parts.append(f"\nCONVERSION ACTIONS ({len(conv_actions)}):")
            for ca in conv_actions:
                included = "✓ included" if ca.get("include_in_conversions") else "✗ excluded"
                attr = ca.get("attribution_model", "N/A")
                parts.append(
                    f"  {ca['name']} (ID:{ca['action_id']}) — "
                    f"Type:{ca['type']} | Status:{ca['status']} | Category:{ca['category']} | "
                    f"Counting:{ca.get('counting_type', 'N/A')} | Attribution:{attr} | {included} | "
                    f"Click lookback:{ca.get('click_through_lookback_days', 'N/A')}d | "
                    f"View lookback:{ca.get('view_through_lookback_days', 'N/A')}d"
                )

        return "\n".join(parts)

    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        """Parse Claude's JSON response, handling edge cases."""
        # Try direct JSON parse
        text = raw_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Fallback: return as plain message
        logger.warning("Could not parse Claude response as JSON", text_preview=text[:200])
        return {
            "summary": text[:500] if len(text) > 500 else text,
            "findings": [],
            "recommended_actions": [],
            "questions": [],
            "message": text,
        }
