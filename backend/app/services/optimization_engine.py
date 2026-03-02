"""
Optimization Engine — Generates and applies recommendations with safety guardrails.

Categories:
1) Waste control (negatives, pause waste)
2) Coverage improvement (missing keywords)
3) Messaging improvement (headline rotation)
4) Bid/budget tuning
5) Targeting refinement (geo, schedule)
6) Structure fixes (split ad groups)
7) Landing page suggestions
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from app.models.recommendation import Recommendation
from app.models.change_log import ChangeLog
from app.models.tenant import Tenant

logger = structlog.get_logger()


class OptimizationEngine:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def apply_recommendation(self, recommendation_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Recommendation).where(
                Recommendation.id == recommendation_id,
                Recommendation.tenant_id == self.tenant_id,
            )
        )
        rec = result.scalar_one_or_none()
        if not rec:
            return {"status": "error", "message": "Recommendation not found"}
        if rec.status not in ("approved", "pending"):
            return {"status": "error", "message": f"Recommendation is {rec.status}"}

        tenant = await self._get_tenant()
        if not tenant:
            return {"status": "error", "message": "Tenant not found"}

        from app.services.guardrails import GuardrailsEngine
        guardrails = GuardrailsEngine(self.db, self.tenant_id)
        safety_check = await guardrails.check_recommendation(rec, tenant)
        if not safety_check["allowed"]:
            rec.status = "blocked"
            return {"status": "blocked", "reason": safety_check["reason"]}

        diff = rec.action_diff_json or {}
        action = diff.get("action", "unknown")

        rollback_token = str(uuid.uuid4())

        change_log = ChangeLog(
            tenant_id=self.tenant_id,
            actor_type="system" if actor_id is None else "user",
            actor_id=actor_id,
            entity_type=diff.get("entity_type", "unknown"),
            entity_id=diff.get("entity_id", ""),
            before_json=diff.get("before", {}),
            after_json=diff.get("after", {}),
            reason=rec.rationale,
            rollback_token=rollback_token,
        )
        self.db.add(change_log)

        apply_result = await self._execute_action(action, diff)

        rec.status = "applied"
        rec.applied_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.info("Recommendation applied", rec_id=recommendation_id, action=action, rollback_token=rollback_token)
        return {"status": "applied", "rollback_token": rollback_token, "result": apply_result}

    async def apply_auto_recommendations(self) -> List[Dict]:
        tenant = await self._get_tenant()
        if not tenant or tenant.autonomy_mode == "suggest":
            return []

        result = await self.db.execute(
            select(Recommendation).where(
                Recommendation.tenant_id == self.tenant_id,
                Recommendation.status == "pending",
            )
        )
        recs = result.scalars().all()
        applied = []

        for rec in recs:
            if self._is_auto_approvable(rec, tenant.autonomy_mode):
                apply_result = await self.apply_recommendation(rec.id)
                if apply_result["status"] == "applied":
                    applied.append({"rec_id": rec.id, "title": rec.title})

        return applied

    def _is_auto_approvable(self, rec: Recommendation, autonomy_mode: str) -> bool:
        if autonomy_mode == "suggest":
            return False

        if autonomy_mode == "semi_auto":
            low_risk_categories = ["waste_control"]
            low_risk_actions = ["add_negative", "pause_keyword", "pause_ad"]
            action = (rec.action_diff_json or {}).get("action", "")
            return (
                rec.risk_level == "low"
                and (rec.category in low_risk_categories or action in low_risk_actions)
            )

        if autonomy_mode == "full_auto":
            return rec.risk_level in ("low", "medium")

        return False

    async def _execute_action(self, action: str, diff: Dict) -> Dict[str, Any]:
        if action == "pause_keywords":
            keyword_ids = diff.get("keyword_ids", [])
            logger.info("Pausing keywords", count=len(keyword_ids))
            return {"action": "pause_keywords", "count": len(keyword_ids)}

        elif action == "add_negative":
            negatives = diff.get("negatives", [])
            logger.info("Adding negatives", count=len(negatives))
            return {"action": "add_negative", "count": len(negatives)}

        elif action == "adjust_bid":
            logger.info("Adjusting bid", entity_id=diff.get("entity_id"))
            return {"action": "adjust_bid", "entity_id": diff.get("entity_id")}

        elif action == "adjust_budget":
            logger.info("Adjusting budget", entity_id=diff.get("entity_id"))
            return {"action": "adjust_budget", "entity_id": diff.get("entity_id")}

        elif action == "pause_ad":
            logger.info("Pausing ad", entity_id=diff.get("entity_id"))
            return {"action": "pause_ad", "entity_id": diff.get("entity_id")}

        else:
            logger.warning("Unknown action type", action=action)
            return {"action": action, "status": "not_implemented"}

    async def rollback_change(self, change_log_id: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
        result = await self.db.execute(
            select(ChangeLog).where(
                ChangeLog.id == change_log_id,
                ChangeLog.tenant_id == self.tenant_id,
            )
        )
        log = result.scalar_one_or_none()
        if not log:
            return {"status": "error", "message": "Change log not found"}
        if log.is_rolled_back:
            return {"status": "error", "message": "Already rolled back"}

        rollback_log = ChangeLog(
            tenant_id=self.tenant_id,
            actor_type="user",
            actor_id=actor_id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            before_json=log.after_json,
            after_json=log.before_json,
            reason=f"Rollback of change {log.id}",
            rollback_token=str(uuid.uuid4()),
        )
        self.db.add(rollback_log)

        log.is_rolled_back = True
        await self.db.flush()

        logger.info("Change rolled back", original_id=change_log_id)
        return {"status": "rolled_back", "original_change": change_log_id}

    async def _get_tenant(self) -> Optional[Tenant]:
        result = await self.db.execute(select(Tenant).where(Tenant.id == self.tenant_id))
        return result.scalar_one_or_none()
