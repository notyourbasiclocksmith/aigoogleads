from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
import structlog

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser

logger = structlog.get_logger()
router = APIRouter()


class GenerateReportRequest(BaseModel):
    report_type: str = "weekly"  # weekly, monthly, weekly_digest
    period_days: int = 7


@router.post("/generate")
async def generate_report(
    req: GenerateReportRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a report synchronously and return it. Also tries Celery for PDF/email."""
    from app.services.report_service import ReportService
    svc = ReportService(db, user.tenant_id)
    period_days = req.period_days or 7

    try:
        report_data = await svc.generate_weekly_report(period_days)
    except Exception as e:
        logger.error("Report generation failed", error=str(e), tenant_id=user.tenant_id)
        report_data = None

    # Try to queue Celery for PDF/email in background (non-blocking)
    try:
        from app.jobs.tasks import generate_report_task
        generate_report_task.delay(user.tenant_id, req.report_type, period_days)
    except Exception:
        pass  # Celery may not be running locally

    if report_data:
        return {
            "status": "delivered",
            "report_type": req.report_type,
            "period_start": report_data.get("period", {}).get("start"),
            "period_end": report_data.get("period", {}).get("end"),
            "summary_json": {
                "headline": report_data.get("ai_narrative", {}).get("executive_summary", "") if report_data.get("ai_narrative") else f"{report_data.get('kpis', {}).get('current', {}).get('clicks', 0)} clicks, {report_data.get('kpis', {}).get('current', {}).get('conversions', 0)} conversions",
                "key_findings": (
                    report_data.get("ai_narrative", {}).get("next_week_plan", [])
                    if report_data.get("ai_narrative")
                    else report_data.get("next_week_focus", [])
                ),
                "health_score": report_data.get("ai_narrative", {}).get("health_score") if report_data.get("ai_narrative") else None,
                "trend": report_data.get("ai_narrative", {}).get("trend_direction") if report_data.get("ai_narrative") else None,
            },
            "full_report": report_data,
        }

    return {"status": "generating", "message": "Report is being generated in the background."}


@router.get("")
async def list_reports(
    report_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.models.asset import Asset
    from sqlalchemy import select, desc

    query = select(Asset).where(
        Asset.tenant_id == user.tenant_id,
        Asset.asset_type == "REPORT",
    )
    if report_type:
        query = query.where(Asset.metadata_json["report_type"].astext == report_type)
    query = query.order_by(desc(Asset.created_at)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    reports = result.scalars().all()
    return [
        {
            "id": r.id,
            "report_type": (r.metadata_json or {}).get("report_type", "weekly"),
            "status": (r.metadata_json or {}).get("status", "delivered"),
            "period_start": (r.metadata_json or {}).get("period_start"),
            "period_end": (r.metadata_json or {}).get("period_end"),
            "pdf_url": r.url,
            "summary_json": (r.metadata_json or {}).get("summary_json"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@router.get("/latest")
async def latest_report(
    period_days: int = Query(7, ge=1, le=90),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate and return a fresh report on demand (no storage)."""
    from app.services.report_service import ReportService
    svc = ReportService(db, user.tenant_id)
    try:
        report_data = await svc.generate_weekly_report(period_days)
        return {
            "status": "delivered",
            "report_type": "weekly",
            "period_start": report_data.get("period", {}).get("start"),
            "period_end": report_data.get("period", {}).get("end"),
            "summary_json": {
                "headline": report_data.get("ai_narrative", {}).get("executive_summary", "") if report_data.get("ai_narrative") else "Report generated",
                "key_findings": (
                    report_data.get("ai_narrative", {}).get("next_week_plan", [])
                    if report_data.get("ai_narrative")
                    else report_data.get("next_week_focus", [])
                ),
            },
            "full_report": report_data,
        }
    except Exception as e:
        logger.error("Latest report generation failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate report")


@router.get("/export/csv")
async def export_csv(
    entity_type: str = Query("campaigns", regex="^(campaigns|keywords|search_terms|ads|auction_insights|campaign|ad_group|ad|keyword)$"),
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.services.report_service import ReportService
    svc = ReportService(db, user.tenant_id)
    csv_data = await svc.export_csv(entity_type, days)
    from fastapi.responses import StreamingResponse
    import io
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={entity_type}_{days}d.csv"},
    )
