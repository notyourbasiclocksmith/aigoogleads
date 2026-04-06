"""
Unified Claude Agent Service — multi-system prompt, structured response parsing.

Handles Auto mode (cross-channel) and single-channel modes with one agent.
"""
import json
from typing import Dict, Any, List, Optional
import structlog
import anthropic

from app.core.config import settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are the Unified Marketing Operator for IntelliAds — an AI-powered marketing platform.

You have access to multiple connected marketing systems. Your job is to help users manage their entire marketing stack through conversation.

CONNECTED SYSTEMS YOU MAY HAVE DATA FOR:
- **Google Ads**: campaigns, ad groups, keywords, search terms, ads, performance (impressions, clicks, cost, conversions, CTR, CPC, CPA, ROAS)
- **Meta Ads (Facebook/Instagram)**: campaigns, ad sets, ads, creatives, audiences, performance (impressions, clicks, spend, reach, CPC, CPM, CTR, conversions, frequency)
- **Google Business Profile (GBP)**: business info, reviews, posts, local insights
- **Image Generation**: AI image creation for ads and social posts (DALLE, Stability AI, Flux)

RULES:
1. Only base recommendations on provided data. Never invent campaigns, keywords, metrics, or reviews.
2. Think in terms of OUTCOMES: more leads, less wasted spend, better local presence, stronger creative.
3. When multiple systems are available, analyze across all of them to find the best opportunities.
4. Prioritize: wasted spend reduction > conversion improvement > reach/CTR improvement > content freshness.
5. Separate findings from actions. Group findings by system.
6. All write actions require explicit confirmation — mark requires_confirmation: true.
7. Be concise, practical, and operator-focused. No fluff.
8. If a system's data is unavailable, work with what you have. Mention what's missing.
9. Only reference entity IDs that appear in the provided data.
10. For image generation, describe what you'd create but do not fabricate URLs.

RESPONSE FORMAT:
Always respond with valid JSON matching this schema:
{
  "summary": "1-3 sentence overview",
  "findings": [
    {
      "system": "google_ads|meta_ads|gbp|image|general",
      "type": "wasted_spend|low_ctr|high_frequency|audience_fatigue|budget_opportunity|creative_fatigue|reputation_gap|missing_content|poor_targeting|low_quality|other",
      "title": "Short title",
      "description": "Explanation",
      "severity": "high|medium|low",
      "data": []
    }
  ],
  "recommended_actions": [
    {
      "system": "google_ads|meta_ads|gbp|image",
      "action_type": "see action types below",
      "label": "Human-readable label",
      "reasoning": "Why this action",
      "risk_level": "low|medium|high",
      "requires_confirmation": true,
      "expected_impact": "Expected outcome",
      "payload": {}
    }
  ],
  "questions": [],
  "message": "optional conversational follow-up"
}

SUPPORTED ACTION TYPES BY SYSTEM:

Google Ads:
- pause_keyword, enable_keyword, add_negative_keyword
- update_campaign_budget, pause_campaign, enable_campaign
- create_campaign, create_ad_group, create_responsive_search_ad, add_keywords

Meta Ads:
- pause_meta_campaign, enable_meta_campaign, update_meta_budget
- create_meta_campaign, create_meta_adset, create_meta_ad
- generate_meta_creative

GBP:
- reply_review, reply_reviews_batch, generate_review_reply
- create_gbp_post, generate_gbp_post

Image:
- generate_ad_image, generate_social_image

PAYLOAD FORMATS:
- pause_keyword: {"keyword_ids": [...], "ad_group_id": "..."}
- add_negative_keyword: {"terms": [...], "campaign_id": "..."}
- update_campaign_budget: {"campaign_id": "...", "new_daily_budget": 50.00}
- pause_campaign / enable_campaign: {"campaign_id": "..."}
- pause_meta_campaign / enable_meta_campaign: {"campaign_id": "..."}
- update_meta_budget: {"campaign_id": "...", "new_daily_budget_cents": 5000}
- create_meta_campaign: {"name": "...", "objective": "OUTCOME_LEADS", "daily_budget_cents": 2000}
- reply_review: {"review_id": "...", "reply_text": "..."}
- reply_reviews_batch: {"reviews": [{"review_id": "...", "reviewer_name": "...", "star_rating": 5, "comment": "..."}]}
- generate_review_reply: {"review_id": "...", "reviewer_name": "...", "star_rating": 5, "comment": "...", "tone": "professional"}
- create_gbp_post: {"summary": "...", "topic_type": "STANDARD"}
- generate_gbp_post: {"topic": "...", "include_image": true}
- generate_ad_image: {"service": "...", "business_name": "...", "engine": "dalle"}
- generate_social_image: {"topic": "...", "platform": "instagram"}

IMPORTANT: Only use entity IDs from the provided data. Never fabricate IDs."""


class UnifiedAgentService:
    """Unified Claude agent for multi-system marketing analysis."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL

    async def analyze(
        self,
        user_message: str,
        context: Dict[str, Any],
        systems_used: List[str],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Send user message + multi-system context to Claude."""
        logger.info("unified_agent_call", systems=systems_used, msg_preview=user_message[:80])

        context_text = self._format_context(context, systems_used)

        messages = []
        if conversation_history:
            for msg in conversation_history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        user_content = f"""CONNECTED SYSTEMS: {', '.join(systems_used)}

LIVE ACCOUNT DATA:
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
            logger.info("unified_agent_response", length=len(raw_text))
            return self._parse_response(raw_text)

        except anthropic.APIError as e:
            logger.error("unified_agent_api_error", error=str(e))
            return self._error_response(f"API error: {str(e)[:200]}")
        except Exception as e:
            logger.error("unified_agent_error", error=str(e))
            return self._error_response(f"Error: {str(e)[:200]}")

    def _format_context(self, ctx: Dict[str, Any], systems: List[str]) -> str:
        """Format multi-system context into text for Claude."""
        parts = []

        # System availability
        errors = ctx.get("system_errors", {})
        if errors:
            parts.append("UNAVAILABLE SYSTEMS:")
            for sys, err in errors.items():
                parts.append(f"  {sys}: {err}")
            parts.append("")

        # Google Ads
        gads = ctx.get("google_ads", {})
        if gads.get("connected"):
            parts.append("═══ GOOGLE ADS ═══")
            acc = gads.get("account", {})
            parts.append(f"Account: {acc.get('name', 'N/A')} (ID: {gads.get('customer_id', 'N/A')})")

            h = gads.get("heuristics", {})
            if h:
                parts.append(f"Wasted keywords: {h.get('wasted_keyword_count', 0)} (${h.get('wasted_keyword_spend', 0)})")
                parts.append(f"Low CTR ads: {h.get('low_ctr_ad_count', 0)}")
                parts.append(f"Negative KW opportunities: {h.get('negative_keyword_opportunities', 0)}")

            for c in gads.get("campaign_performance", []):
                parts.append(
                    f"  [{c['status']}] {c['name']} (ID:{c['campaign_id']}) — "
                    f"Budget:${c['daily_budget']}/day | Cost:${c['cost']} | "
                    f"Clicks:{c['clicks']} | CTR:{c['ctr']}% | Conv:{c['conversions']} | CPA:${c['cost_per_conversion']}"
                )

            for k in gads.get("keyword_performance", [])[:25]:
                qs = f" QS:{k['quality_score']}" if k.get("quality_score") else ""
                parts.append(
                    f"  KW [{k['match_type']}] \"{k['text']}\" (ID:{k['keyword_id']}) — "
                    f"${k['cost']} | {k['clicks']}cl | Conv:{k['conversions']}{qs}"
                )

            for t in gads.get("search_terms", [])[:20]:
                parts.append(
                    f"  ST \"{t['search_term']}\" — ${t['cost']} | {t['clicks']}cl | Conv:{t['conversions']}"
                )
            parts.append("")

        # Meta Ads
        meta = ctx.get("meta_ads", {})
        if meta.get("connected"):
            parts.append("═══ META ADS ═══")
            acc = meta.get("account", {})
            parts.append(f"Account: {acc.get('name', 'N/A')} (ID: {meta.get('ad_account_id', 'N/A')})")

            h = meta.get("heuristics", {})
            if h:
                parts.append(f"Total Spend: ${h.get('total_spend', 0)} | Clicks: {h.get('total_clicks', 0)} | CTR: {h.get('avg_ctr', 0)}% | CPC: ${h.get('avg_cpc', 0)}")
                parts.append(f"Campaigns: {h.get('campaign_count', 0)} ({h.get('active_campaigns', 0)} active)")

            for c in meta.get("campaigns", []):
                budget = c.get("daily_budget") or c.get("lifetime_budget") or "N/A"
                parts.append(f"  [{c.get('status')}] {c.get('name')} (ID:{c.get('id')}) — Obj:{c.get('objective')} | Budget:{budget}")

            for p in meta.get("performance", []):
                parts.append(
                    f"  PERF {p.get('campaign_name', 'N/A')} — Spend:${p.get('spend', 0)} | "
                    f"Clicks:{p.get('clicks', 0)} | CTR:{p.get('ctr', 0)}% | Reach:{p.get('reach', 0)}"
                )
            parts.append("")

        # GBP
        gbp = ctx.get("gbp", {})
        if gbp.get("connected"):
            parts.append("═══ GOOGLE BUSINESS PROFILE ═══")
            info = gbp.get("business_info", {})
            parts.append(f"Business: {info.get('title', 'N/A')}")
            parts.append(f"Phone: {info.get('phone', 'N/A')} | Web: {info.get('website', 'N/A')}")

            rs = gbp.get("review_summary", {})
            parts.append(f"Reviews: {rs.get('total', 0)} total | Avg: {rs.get('average_rating', 0)} stars | Unanswered: {rs.get('unanswered', 0)}")

            for r in gbp.get("reviews", [])[:10]:
                reply_status = "REPLIED" if r.get("reply") else "NO REPLY"
                parts.append(f"  [{reply_status}] {r.get('star_rating', '?')}★ by {r.get('reviewer_name', 'Anon')} — \"{(r.get('comment', '') or '')[:80]}\"")

            posts = gbp.get("posts", [])
            if posts:
                parts.append(f"Recent Posts: {len(posts)}")
                for p in posts[:5]:
                    parts.append(f"  [{p.get('state', '?')}] {p.get('summary', '')[:60]}")
            parts.append("")

        # Image
        img = ctx.get("image", {})
        if img.get("available"):
            parts.append("═══ IMAGE GENERATION ═══")
            parts.append(f"Available: Yes | Engines: {', '.join(img.get('engines', []))}")
            parts.append(f"Capabilities: {', '.join(img.get('capabilities', []))}")
            parts.append("")

        return "\n".join(parts) if parts else "No system data available."

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

        logger.warning("unified_agent_json_parse_failed", preview=text[:200])
        return {
            "summary": text[:500] if len(text) > 500 else text,
            "findings": [],
            "recommended_actions": [],
            "questions": [],
            "message": text,
        }

    @staticmethod
    def _error_response(msg: str) -> Dict[str, Any]:
        return {
            "summary": "I encountered an error during analysis.",
            "findings": [],
            "recommended_actions": [],
            "questions": [],
            "message": msg,
        }
