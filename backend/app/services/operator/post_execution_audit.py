"""
Post-Execution Audit Agent
===========================

After a campaign is deployed to Google Ads, this agent:
1. Fetches the ACTUAL created entities from the Google Ads API
2. Compares them against the intended spec
3. Identifies issues (missing keywords, truncated headlines, failed extensions)
4. Generates fix mutations if problems found
5. Returns audit results for display in the UI

CONDITIONAL TRIGGERS (not every campaign gets audited):
- Campaign budget >= $50/day
- Pipeline QA score < 85
- First campaign for the account
- Random 20% sampling
"""

import json
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import anthropic
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import settings
from app.models.operator import OperatorMessage, ProposedAction

logger = structlog.get_logger()


class PostExecutionAuditAgent:
    """Audits deployed campaigns by comparing Google Ads reality vs intended spec."""

    def __init__(self, db: AsyncSession, ads_client: Any, tenant_id: str):
        self.db = db
        self.ads_client = ads_client
        self.tenant_id = tenant_id
        self.claude = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        # Audit agent uses Opus — correctness matters here
        self.model = "claude-opus-4-6"

    # ── CONDITIONAL TRIGGER ─────────────────────────────────────

    async def should_audit(
        self,
        spec: Dict[str, Any],
        deploy_result: Dict[str, Any],
        pipeline_metadata: Optional[Dict] = None,
    ) -> bool:
        """Determine if this campaign warrants a post-execution audit."""
        reasons = []

        # 1. Budget >= $50/day
        budget_micros = spec.get("campaign", {}).get("budget_micros", 0)
        budget_daily = budget_micros / 1_000_000
        if budget_daily >= 50:
            reasons.append(f"high_budget (${budget_daily}/day)")

        # 2. QA score < 85
        qa_score = (pipeline_metadata or {}).get("qa_score")
        if qa_score is not None and qa_score < 85:
            reasons.append(f"low_qa_score ({qa_score})")

        # 3. First campaign for account
        try:
            campaigns = await self.ads_client.get_campaigns()
            # If there are very few campaigns, this is likely a new account
            if len(campaigns) <= 2:
                reasons.append("new_account")
        except Exception:
            pass

        # 4. Deployment had errors (partial success)
        if deploy_result.get("errors"):
            reasons.append(f"deploy_errors ({len(deploy_result['errors'])})")

        # 5. Random 20% sampling
        if not reasons and random.random() < 0.20:
            reasons.append("random_sample")

        if reasons:
            logger.info("Audit triggered", reasons=reasons)
            return True

        logger.info("Audit skipped — no trigger conditions met")
        return False

    # ── FETCH ACTUAL STATE FROM GOOGLE ADS ──────────────────────

    async def _fetch_deployed_state(self, campaign_id: str) -> Dict[str, Any]:
        """Fetch what was ACTUALLY created in Google Ads."""
        state: Dict[str, Any] = {"campaign": None, "ad_groups": [], "errors": []}

        try:
            # Get the campaign
            campaigns = await self.ads_client.get_campaigns()
            campaign = next((c for c in campaigns if c["campaign_id"] == campaign_id), None)
            state["campaign"] = campaign

            if not campaign:
                state["errors"].append(f"Campaign {campaign_id} not found in Google Ads")
                return state

            # Get ad groups
            ad_groups = await self.ads_client.get_ad_groups(campaign_id)
            for ag in ad_groups:
                ag_detail: Dict[str, Any] = {
                    "ad_group_id": ag["ad_group_id"],
                    "name": ag["name"],
                    "status": ag["status"],
                    "keywords": [],
                    "ads": [],
                }

                # Get keywords for this ad group
                try:
                    keywords = await self.ads_client.get_keywords(ag["ad_group_id"])
                    ag_detail["keywords"] = keywords
                except Exception as e:
                    state["errors"].append(f"Keywords fetch failed for {ag['name']}: {str(e)[:100]}")

                # Get ads for this ad group
                try:
                    ads = await self.ads_client.get_ads(ag["ad_group_id"])
                    ag_detail["ads"] = ads
                except Exception as e:
                    state["errors"].append(f"Ads fetch failed for {ag['name']}: {str(e)[:100]}")

                state["ad_groups"].append(ag_detail)

        except Exception as e:
            state["errors"].append(f"State fetch failed: {str(e)[:200]}")

        return state

    # ── CLAUDE AUDIT AGENT ──────────────────────────────────────

    async def run_audit(
        self,
        spec: Dict[str, Any],
        deploy_result: Dict[str, Any],
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Full audit flow: fetch actual state → compare with spec → generate fixes."""
        campaign_id = deploy_result.get("campaign", {}).get("campaign_id")
        if not campaign_id:
            return {"status": "skipped", "reason": "No campaign_id in deploy result"}

        # Emit progress
        await self._emit_progress(conversation_id, "running",
            "Fetching deployed campaign from Google Ads API for verification...")

        # Fetch what actually exists in Google Ads
        actual_state = await self._fetch_deployed_state(campaign_id)

        await self._emit_progress(conversation_id, "running",
            f"Comparing {len(actual_state.get('ad_groups', []))} ad groups against intended spec...")

        # Call Claude to compare spec vs actual
        audit_result = await self._claude_audit(spec, actual_state, deploy_result)

        if not audit_result:
            await self._emit_progress(conversation_id, "done",
                "Audit complete — could not parse results")
            return {"status": "error", "reason": "Claude audit failed to return valid JSON"}

        # Generate fix actions if issues found
        fix_actions = []
        if audit_result.get("issues"):
            fix_actions = await self._generate_fixes(
                audit_result, spec, actual_state, campaign_id
            )

        status = audit_result.get("status", "valid")
        issue_count = len(audit_result.get("issues", []))
        fix_count = len(fix_actions)

        await self._emit_progress(conversation_id, "done",
            f"Audit: {status.upper()} — {issue_count} issues found, {fix_count} auto-fixes generated"
            if issue_count > 0
            else "Audit: PASSED — campaign deployed correctly")

        # Save audit result as a message
        await self._save_audit_message(conversation_id, audit_result, fix_actions)

        return {
            "status": status,
            "score": audit_result.get("score", 100),
            "issues": audit_result.get("issues", []),
            "fix_actions": fix_actions,
            "actual_state_summary": {
                "ad_groups": len(actual_state.get("ad_groups", [])),
                "total_keywords": sum(
                    len(ag.get("keywords", []))
                    for ag in actual_state.get("ad_groups", [])
                ),
                "total_ads": sum(
                    len(ag.get("ads", []))
                    for ag in actual_state.get("ad_groups", [])
                ),
                "fetch_errors": len(actual_state.get("errors", [])),
            },
        }

    async def _claude_audit(
        self,
        spec: Dict[str, Any],
        actual_state: Dict[str, Any],
        deploy_result: Dict[str, Any],
    ) -> Optional[Dict]:
        """Claude compares intended spec vs actual deployed state."""

        system = """You are a Google Ads deployment verification agent. Your job is to compare
what was INTENDED (the campaign spec) against what was ACTUALLY CREATED in Google Ads.

Think step by step:
1. Was the campaign created? Check name, status, budget, bidding strategy.
2. Were ALL ad groups created? Compare count and names.
3. For each ad group:
   - Were all keywords added? Compare count and texts.
   - Were RSAs created with the right number of headlines/descriptions?
   - Are final_urls set correctly?
4. Were sitelinks, callouts, and structured snippets attached?
5. Were there any deployment errors?

For each issue, classify severity:
- "critical": Something is MISSING or BROKEN — campaign won't perform (missing ad group, no keywords, no ads)
- "warning": Suboptimal but campaign will run (fewer keywords than intended, missing callout)
- "info": Minor discrepancy that doesn't affect performance

Also check for UNEXPECTED issues:
- Keywords that were added but shouldn't have been
- Duplicate keywords across ad groups
- Headlines that got truncated or changed

Respond with ONLY valid JSON."""

        # Clean spec for comparison — remove internal metadata
        clean_spec = {k: v for k, v in spec.items() if not k.startswith("_")}

        user_msg = f"""INTENDED SPEC (what we MEANT to create):
{json.dumps(clean_spec, indent=2, default=str)[:8000]}

DEPLOYMENT RESULT (API response during creation):
{json.dumps(deploy_result, indent=2, default=str)[:3000]}

ACTUAL STATE (fetched from Google Ads API after deployment):
{json.dumps(actual_state, indent=2, default=str)[:8000]}

Return this JSON:
{{
  "status": "valid" | "issues_found",
  "score": 0-100,
  "summary": "1-2 sentence assessment",
  "issues": [
    {{
      "severity": "critical" | "warning" | "info",
      "category": "missing_ad_group" | "missing_keywords" | "missing_ads" | "missing_extensions" | "budget_mismatch" | "truncated_copy" | "duplicate_keywords" | "other",
      "description": "What's wrong",
      "intended": "What we wanted",
      "actual": "What we got",
      "fix_type": "add_keywords" | "create_responsive_search_ad" | "create_sitelinks" | "create_callouts" | "update_campaign_budget" | "none",
      "fix_payload": {{}}
    }}
  ],
  "metrics": {{
    "intended_ad_groups": N,
    "actual_ad_groups": N,
    "intended_keywords": N,
    "actual_keywords": N,
    "intended_headlines_per_ad": N,
    "actual_headlines_per_ad": N,
    "extensions_attached": true/false
  }}
}}"""

        try:
            response = await self.claude.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.2,
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(raw)
        except Exception as e:
            logger.error("Claude audit call failed", error=str(e))
            return None

    # ── FIX GENERATION ──────────────────────────────────────────

    async def _generate_fixes(
        self,
        audit_result: Dict,
        spec: Dict,
        actual_state: Dict,
        campaign_id: str,
    ) -> List[Dict[str, Any]]:
        """Convert audit issues into actionable fix mutations."""
        fixes = []

        for issue in audit_result.get("issues", []):
            if issue.get("severity") == "info":
                continue  # Don't generate fixes for info-level issues

            fix_type = issue.get("fix_type", "none")
            if fix_type == "none":
                continue

            fix_payload = issue.get("fix_payload", {})

            # Ensure campaign_id is set for fixes that need it
            if fix_type in ("create_sitelinks", "create_callouts", "create_structured_snippets",
                            "add_negative_keyword", "update_campaign_budget"):
                fix_payload.setdefault("campaign_id", campaign_id)

            fixes.append({
                "action_type": fix_type,
                "label": f"Fix: {issue.get('description', fix_type)[:80]}",
                "reasoning": f"Post-deployment audit found: {issue.get('description', '')}. Intended: {issue.get('intended', 'N/A')}. Actual: {issue.get('actual', 'N/A')}.",
                "expected_impact": "Correct deployment discrepancy to match intended campaign spec",
                "risk_level": "low",
                "action_payload": fix_payload,
            })

        return fixes

    # ── DB HELPERS ──────────────────────────────────────────────

    async def _emit_progress(self, conversation_id: str, status: str, detail: str):
        """Insert an audit progress message."""
        msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=f"Audit: {detail}",
            structured_payload={
                "type": "audit_progress",
                "agent": "Post-Deployment Audit",
                "status": status,
                "detail": detail,
            },
        )
        self.db.add(msg)
        try:
            await self.db.flush()
        except Exception:
            pass

    async def _save_audit_message(
        self,
        conversation_id: str,
        audit_result: Dict,
        fix_actions: List[Dict],
    ):
        """Save the audit result as a chat message with optional fix actions."""
        status = audit_result.get("status", "valid")
        score = audit_result.get("score", 100)
        issues = audit_result.get("issues", [])

        content = audit_result.get("summary", "")
        if not content:
            if status == "valid":
                content = f"Campaign passed post-deployment audit (score: {score}/100)."
            else:
                content = f"Audit found {len(issues)} issue(s) (score: {score}/100). Review recommended."

        msg = OperatorMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            structured_payload={
                "type": "audit_result",
                "status": status,
                "score": score,
                "issues": issues,
                "metrics": audit_result.get("metrics", {}),
                "fix_count": len(fix_actions),
            },
        )
        self.db.add(msg)
        await self.db.flush()

        # Save fix actions as ProposedActions (user can approve/reject)
        if fix_actions:
            for fix in fix_actions:
                pa = ProposedAction(
                    id=str(uuid.uuid4()),
                    conversation_id=conversation_id,
                    message_id=msg.id,
                    action_type=fix["action_type"],
                    label=fix["label"],
                    reasoning=fix["reasoning"],
                    expected_impact=fix["expected_impact"],
                    risk_level=fix["risk_level"],
                    action_payload=fix["action_payload"],
                    status="proposed",
                )
                self.db.add(pa)
            await self.db.flush()
