"""
Operator Orchestrator — single orchestration layer for the entire
AI Campaign Operator flow:
scan -> analyze -> recommend -> project -> creative audit -> surface to frontend
"""
import structlog
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.v2.operator_scan import OperatorScan
from app.models.v2.operator_recommendation import OperatorRecommendation
from app.models.v2.operator_change_set import OperatorChangeSet
from app.models.v2.creative_audit import CreativeAudit
from app.models import IntegrationGoogleAds, BusinessProfile
from app.models.tenant import Tenant
from app.core.security import decrypt_token

from app.services.operator.schemas import (
    ScanStatus, ScanResult, AccountSnapshot, RecommendationOutput,
)
from app.services.operator.account_scan_service import collect_account_data
from app.services.operator.recommendation_engine import generate_recommendations
from app.services.operator.projection_engine import build_projections, project_selected_changes
from app.services.operator.creative_intelligence_service import run_creative_audit, generate_image_prompts
from app.services.operator.narrative_generator import generate_narrative

logger = structlog.get_logger()


async def run_operator_scan(scan_id: str, db: AsyncSession) -> None:
    """
    Main pipeline: collect data -> analyze -> recommend -> project -> creative audit.
    Called by Celery task. Updates scan status at each stage.
    """
    scan = await db.get(OperatorScan, scan_id)
    if not scan:
        logger.error("Scan not found", scan_id=scan_id)
        return

    try:
        # ── Stage 1: Collect data ────────────────────────────────────────
        await _update_status(db, scan, ScanStatus.COLLECTING_DATA)

        integration = await db.get(IntegrationGoogleAds, scan.account_id)
        if not integration or not integration.refresh_token_encrypted:
            raise ValueError("No connected Google Ads account or missing refresh token")

        refresh_token = decrypt_token(integration.refresh_token_encrypted)
        customer_id = integration.customer_id
        if not customer_id or customer_id == "pending":
            raise ValueError("Google Ads Customer ID not configured")

        campaign_ids = scan.campaign_ids_json if scan.campaign_scope == "selected" else None

        snapshot = await collect_account_data(
            refresh_token=refresh_token,
            customer_id=customer_id,
            date_start=scan.date_range_start,
            date_end=scan.date_range_end,
            campaign_ids=campaign_ids,
            login_customer_id=integration.login_customer_id,
        )

        scan.metrics_snapshot_json = {
            "total_spend": snapshot.total_spend,
            "total_conversions": snapshot.total_conversions,
            "total_clicks": snapshot.total_clicks,
            "total_impressions": snapshot.total_impressions,
            "campaigns": len(snapshot.campaigns),
            "ad_groups": len(snapshot.ad_groups),
            "keywords": len(snapshot.keywords),
            "search_terms": len(snapshot.search_terms),
            "ads": len(snapshot.ads),
        }

        # ── Stage 2: Analyze + generate recommendations ──────────────────
        await _update_status(db, scan, ScanStatus.GENERATING_RECOMMENDATIONS)

        recommendations = await generate_recommendations(snapshot, scan.scan_goal)

        # ── Stage 3: Build projections ───────────────────────────────────
        await _update_status(db, scan, ScanStatus.BUILDING_PROJECTIONS)

        summary = build_projections(snapshot, recommendations)

        # ── Stage 4: Creative audit ──────────────────────────────────────
        await _update_status(db, scan, ScanStatus.RUNNING_CREATIVE_AUDIT)

        business_context = await _get_business_context(db, scan.tenant_id)
        creative_result = await run_creative_audit(snapshot, business_context)
        image_prompts = await generate_image_prompts(snapshot, business_context)

        # ── Stage 5: Generate narrative ──────────────────────────────────
        narrative = await generate_narrative(snapshot, summary, recommendations, business_context)

        # ── Persist results ──────────────────────────────────────────────
        # Save recommendations to DB
        for rec in recommendations:
            db_rec = OperatorRecommendation(
                scan_id=scan.id,
                tenant_id=scan.tenant_id,
                recommendation_type=rec.recommendation_type.value,
                group_name=rec.group_name.value,
                entity_type=rec.entity_type,
                entity_id=rec.entity_id,
                entity_name=rec.entity_name,
                parent_entity_id=rec.parent_entity_id,
                title=rec.title,
                rationale=rec.rationale,
                evidence_json=rec.evidence,
                current_state_json=rec.current_state,
                proposed_state_json=rec.proposed_state,
                confidence_score=rec.confidence_score,
                risk_level=rec.risk_level.value,
                impact_projection_json=rec.impact.model_dump(),
                generated_by=rec.generated_by,
                policy_flags_json=rec.policy_flags,
                prerequisites_json=rec.prerequisites,
                priority_order=rec.priority_order,
            )
            db.add(db_rec)

        # Save creative audits
        for audit in creative_result.get("campaign_audits", []):
            db_audit = CreativeAudit(
                scan_id=scan.id,
                tenant_id=scan.tenant_id,
                entity_type="campaign",
                entity_id=audit.get("campaign_id"),
                entity_name=audit.get("campaign_name"),
                copy_audit_json=audit,
                image_prompt_pack_json=image_prompts,
            )
            db.add(db_audit)

        # Update scan with final results
        scan.summary_json = summary.model_dump()
        scan.narrative_summary = narrative
        scan.confidence_score = summary.confidence_score
        scan.risk_score = summary.risk_score
        scan.completed_at = datetime.now(timezone.utc)

        await _update_status(db, scan, ScanStatus.READY)

        logger.info(
            "Operator scan completed",
            scan_id=scan_id,
            recommendations=len(recommendations),
            spend_analyzed=summary.spend_analyzed,
        )

    except Exception as ex:
        logger.error("Operator scan failed", scan_id=scan_id, error=str(ex))
        scan.status = ScanStatus.FAILED.value
        scan.error_message = str(ex)
        await db.commit()


async def create_change_set(
    scan_id: str,
    selected_recommendation_ids: List[str],
    approved_by: Optional[str],
    db: AsyncSession,
    edited_overrides: Optional[Dict[str, Any]] = None,
) -> OperatorChangeSet:
    """Create a change set from selected recommendations."""
    scan = await db.get(OperatorScan, scan_id)
    if not scan:
        raise ValueError("Scan not found")

    # Build projection for selected only
    recs_q = await db.execute(
        select(OperatorRecommendation).where(
            OperatorRecommendation.id.in_(selected_recommendation_ids)
        )
    )
    recs = list(recs_q.scalars().all())

    # Convert DB recs to schema for projection
    schema_recs = []
    for r in recs:
        from app.services.operator.schemas import ImpactProjection, RecType, RecGroup, RiskLevel
        schema_recs.append(RecommendationOutput(
            recommendation_type=RecType(r.recommendation_type),
            group_name=RecGroup(r.group_name),
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            entity_name=r.entity_name,
            title=r.title,
            rationale=r.rationale or "",
            impact=ImpactProjection(**(r.impact_projection_json or {})),
            confidence_score=r.confidence_score,
            risk_level=RiskLevel(r.risk_level),
        ))

    # Rebuild snapshot from scan metrics for projection
    snapshot = AccountSnapshot(
        customer_id="",
        date_range_start=scan.date_range_start,
        date_range_end=scan.date_range_end,
        total_spend=scan.metrics_snapshot_json.get("total_spend", 0),
        total_conversions=scan.metrics_snapshot_json.get("total_conversions", 0),
        total_clicks=scan.metrics_snapshot_json.get("total_clicks", 0),
        total_impressions=scan.metrics_snapshot_json.get("total_impressions", 0),
    )
    projection = project_selected_changes(snapshot, schema_recs)

    cs = OperatorChangeSet(
        scan_id=scan_id,
        tenant_id=scan.tenant_id,
        account_id=scan.account_id,
        approved_by=approved_by,
        selected_recommendation_ids=selected_recommendation_ids,
        edited_overrides_json=edited_overrides or {},
        projection_summary_json=projection,
        status="draft",
    )
    db.add(cs)

    # Mark recommendations as approved
    for r in recs:
        r.status = "approved"

    await db.commit()
    await db.refresh(cs)
    return cs


async def get_scan_result(scan_id: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
    """Get the full scan result for the frontend."""
    scan = await db.get(OperatorScan, scan_id)
    if not scan:
        return None

    recs_q = await db.execute(
        select(OperatorRecommendation)
        .where(OperatorRecommendation.scan_id == scan_id)
        .order_by(OperatorRecommendation.priority_order)
    )
    recs = list(recs_q.scalars().all())

    audits_q = await db.execute(
        select(CreativeAudit).where(CreativeAudit.scan_id == scan_id)
    )
    audits = list(audits_q.scalars().all())

    # Group recommendations
    grouped: Dict[str, List[Dict]] = {}
    for r in recs:
        group = r.group_name
        if group not in grouped:
            grouped[group] = []
        grouped[group].append({
            "id": r.id,
            "type": r.recommendation_type,
            "group": r.group_name,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "entity_name": r.entity_name,
            "title": r.title,
            "rationale": r.rationale,
            "evidence": r.evidence_json,
            "current_state": r.current_state_json,
            "proposed_state": r.proposed_state_json,
            "confidence": r.confidence_score,
            "risk_level": r.risk_level,
            "impact": r.impact_projection_json,
            "generated_by": r.generated_by,
            "status": r.status,
            "priority": r.priority_order,
        })

    return {
        "scan_id": scan.id,
        "status": scan.status,
        "date_range": {"start": scan.date_range_start, "end": scan.date_range_end},
        "scan_goal": scan.scan_goal,
        "summary": scan.summary_json,
        "narrative": scan.narrative_summary,
        "metrics_snapshot": scan.metrics_snapshot_json,
        "confidence_score": scan.confidence_score,
        "risk_score": scan.risk_score,
        "recommendation_groups": grouped,
        "total_recommendations": len(recs),
        "creative_audits": [
            {
                "entity_name": a.entity_name,
                "copy_audit": a.copy_audit_json,
                "asset_audit": a.asset_audit_json,
                "image_prompts": a.image_prompt_pack_json,
                "generated_creatives": a.generated_creatives_json,
            }
            for a in audits
        ],
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "error_message": scan.error_message,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _update_status(db: AsyncSession, scan: OperatorScan, status: ScanStatus):
    scan.status = status.value
    await db.commit()


async def _get_business_context(db: AsyncSession, tenant_id: str) -> Dict[str, Any]:
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
    )
    bp = result.scalar_one_or_none()
    if bp:
        # Get business name from Tenant (not on BusinessProfile)
        tenant_result = await db.execute(
            select(Tenant.name).where(Tenant.id == tenant_id)
        )
        tenant_name = tenant_result.scalar_one_or_none() or ""

        # Extract city from locations_json if available
        city = ""
        if bp.locations_json:
            locs = bp.locations_json if isinstance(bp.locations_json, list) else bp.locations_json.get("locations", [])
            if locs and isinstance(locs, list) and len(locs) > 0:
                first = locs[0]
                city = first.get("city", "") if isinstance(first, dict) else str(first)

        return {
            "business_name": tenant_name,
            "business_type": bp.industry_classification or "local service business",
            "city": city,
            "services": bp.services_json if bp.services_json else [],
            "website": bp.website_url or "",
        }
    return {}
