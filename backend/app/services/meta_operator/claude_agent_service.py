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

SYSTEM_PROMPT = """You are the Meta Ads Operator for a multi-tenant SaaS platform called IgniteAds.

Your job is to help users manage their Meta (Facebook/Instagram) Ads account through conversation.

You are given live account data including: campaigns, ad sets, ads, creatives, audiences, and performance metrics (impressions, clicks, spend, reach, CPC, CPM, CTR, conversions, frequency, etc.)

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
      "type": "wasted_spend|high_frequency|low_ctr|audience_fatigue|budget_opportunity|creative_fatigue|poor_targeting|other",
      "title": "Short title",
      "description": "Explanation",
      "severity": "high|medium|low",
      "data": [optional array of supporting data points]
    }
  ],
  "recommended_actions": [
    {
      "action_type": "pause_campaign|enable_campaign|update_campaign_budget|pause_adset|create_campaign|create_adset|create_ad|update_creative|refresh_creative",
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
- create_campaign: {"name": "...", "objective": "OUTCOME_LEADS", "daily_budget_cents": 2000}
- create_adset: {"campaign_id": "...", "name": "...", "daily_budget_cents": 2000, "optimization_goal": "LEAD_GENERATION", "targeting": {...}}

IMPORTANT: Only use entity IDs that appear in the provided account data. Never fabricate IDs."""


class ClaudeMetaAgentService:
    """Calls Claude API with Meta Ads account context to produce structured analysis."""

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
            response = self.client.messages.create(
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

        campaigns = ctx.get("campaigns", [])
        if campaigns:
            parts.append(f"\nCAMPAIGNS ({len(campaigns)}):")
            for c in campaigns:
                budget = c.get("daily_budget") or c.get("lifetime_budget") or "N/A"
                parts.append(
                    f"  [{c.get('status')}] {c.get('name')} (ID:{c.get('id')}) — "
                    f"Objective:{c.get('objective')} | Budget:{budget}"
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
