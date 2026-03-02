"""
Guardrails Policy Engine — Non-negotiable safety layer.

Rules:
- Budget cap per tenant/day and % change cap per week (default 10-20%)
- Never increase budget without explicit tenant-defined max
- Never switch to broad match everywhere automatically
- Always preserve conversion tracking health; if broken, stop autopilot and alert
- Require cooldown between major changes (72h) unless emergency
- Always log before/after JSON + rollback token
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog

from app.models.tenant import Tenant
from app.models.change_log import ChangeLog
from app.models.conversion import Conversion
from app.models.recommendation import Recommendation

logger = structlog.get_logger()

MAJOR_CHANGE_COOLDOWN_HOURS = 72
MAX_BUDGET_INCREASE_PCT = 20
BLOCKED_AUTO_ACTIONS = ["switch_all_broad_match", "delete_campaign", "remove_conversion_action"]


class GuardrailsEngine:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def check_recommendation(self, rec: Recommendation, tenant: Tenant) -> Dict[str, Any]:
        checks = [
            await self._check_budget_cap(rec, tenant),
            await self._check_broad_match_safety(rec),
            await self._check_conversion_tracking_health(),
            await self._check_cooldown(rec),
            self._check_blocked_actions(rec),
            self._check_risk_vs_autonomy(rec, tenant),
        ]

        for check in checks:
            if not check["allowed"]:
                logger.warning(
                    "Guardrail blocked recommendation",
                    rec_id=rec.id,
                    reason=check["reason"],
                )
                return check

        return {"allowed": True, "reason": "All guardrails passed"}

    async def _check_budget_cap(self, rec: Recommendation, tenant: Tenant) -> Dict[str, Any]:
        diff = rec.action_diff_json or {}
        action = diff.get("action", "")

        if action in ("adjust_budget", "increase_budget"):
            new_budget = diff.get("after", {}).get("budget_micros", 0)
            old_budget = diff.get("before", {}).get("budget_micros", 0)

            if tenant.daily_budget_cap_micros > 0 and new_budget > tenant.daily_budget_cap_micros:
                return {
                    "allowed": False,
                    "reason": f"New budget (${new_budget / 1_000_000:.2f}) exceeds tenant daily cap (${tenant.daily_budget_cap_micros / 1_000_000:.2f})",
                }

            if old_budget > 0:
                change_pct = ((new_budget - old_budget) / old_budget) * 100
                max_pct = tenant.weekly_change_cap_pct or MAX_BUDGET_INCREASE_PCT
                if change_pct > max_pct:
                    return {
                        "allowed": False,
                        "reason": f"Budget increase ({change_pct:.0f}%) exceeds weekly change cap ({max_pct}%)",
                    }

        return {"allowed": True, "reason": "Budget within limits"}

    async def _check_broad_match_safety(self, rec: Recommendation) -> Dict[str, Any]:
        diff = rec.action_diff_json or {}
        action = diff.get("action", "")

        if action == "change_match_type":
            new_match = diff.get("after", {}).get("match_type", "")
            scope = diff.get("scope", "single")
            if new_match == "BROAD" and scope in ("all", "campaign", "ad_group"):
                return {
                    "allowed": False,
                    "reason": "Cannot automatically switch all keywords to broad match. This requires manual approval.",
                }

        return {"allowed": True, "reason": "Match type change is safe"}

    async def _check_conversion_tracking_health(self) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Conversion).where(
                Conversion.tenant_id == self.tenant_id,
                Conversion.is_primary == True,
                Conversion.status == "ENABLED",
            )
        )
        conversions = result.scalars().all()

        if not conversions:
            return {
                "allowed": False,
                "reason": "No active primary conversion tracking. Autopilot changes blocked until tracking is restored.",
            }

        return {"allowed": True, "reason": "Conversion tracking is healthy"}

    async def _check_cooldown(self, rec: Recommendation) -> Dict[str, Any]:
        diff = rec.action_diff_json or {}
        action = diff.get("action", "")

        major_actions = [
            "adjust_budget", "increase_budget", "change_bidding_strategy",
            "change_match_type", "restructure_campaign", "enable_campaign",
        ]

        if action not in major_actions:
            return {"allowed": True, "reason": "Non-major action, no cooldown needed"}

        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(hours=MAJOR_CHANGE_COOLDOWN_HOURS)
        result = await self.db.execute(
            select(func.count()).select_from(ChangeLog).where(and_(
                ChangeLog.tenant_id == self.tenant_id,
                ChangeLog.applied_at >= cooldown_cutoff,
                ChangeLog.actor_type == "system",
            ))
        )
        recent_changes = result.scalar() or 0

        if recent_changes > 3:
            return {
                "allowed": False,
                "reason": f"Cooldown active: {recent_changes} system changes in the last {MAJOR_CHANGE_COOLDOWN_HOURS}h. Wait before applying more major changes.",
            }

        return {"allowed": True, "reason": "Cooldown period clear"}

    def _check_blocked_actions(self, rec: Recommendation) -> Dict[str, Any]:
        diff = rec.action_diff_json or {}
        action = diff.get("action", "")

        if action in BLOCKED_AUTO_ACTIONS:
            return {
                "allowed": False,
                "reason": f"Action '{action}' is permanently blocked from automation.",
            }

        return {"allowed": True, "reason": "Action is not blocked"}

    def _check_risk_vs_autonomy(self, rec: Recommendation, tenant: Tenant) -> Dict[str, Any]:
        if tenant.autonomy_mode == "suggest":
            return {
                "allowed": False,
                "reason": "Tenant is in Suggest mode. All changes require manual approval.",
            }

        if tenant.autonomy_mode == "semi_auto" and rec.risk_level in ("medium", "high"):
            return {
                "allowed": False,
                "reason": f"Semi-auto mode does not allow {rec.risk_level}-risk changes. Manual approval required.",
            }

        if tenant.autonomy_mode == "full_auto" and rec.risk_level == "high":
            if tenant.risk_tolerance == "low":
                return {
                    "allowed": False,
                    "reason": "Full-auto with low risk tolerance blocks high-risk changes.",
                }

        return {"allowed": True, "reason": "Risk level compatible with autonomy mode"}

    async def validate_campaign_launch(self, campaign_budget_micros: int, tenant: Tenant) -> Dict[str, Any]:
        if tenant.daily_budget_cap_micros > 0 and campaign_budget_micros > tenant.daily_budget_cap_micros:
            return {
                "allowed": False,
                "reason": f"Campaign budget exceeds tenant daily cap",
            }

        result = await self.db.execute(
            select(Conversion).where(
                Conversion.tenant_id == self.tenant_id,
                Conversion.is_primary == True,
                Conversion.status == "ENABLED",
            )
        )
        if not result.scalars().first():
            return {
                "allowed": False,
                "reason": "No active conversion tracking. Set up conversions before launching campaigns.",
            }

        return {"allowed": True, "reason": "Campaign launch checks passed"}
