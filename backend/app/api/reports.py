from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import require_tenant, CurrentUser

router = APIRouter()


class GenerateReportRequest(BaseModel):
    report_type: str = "weekly"  # weekly, monthly
    period_days: int = 7


@router.post("/generate")
async def generate_report(
    req: GenerateReportRequest,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.jobs.tasks import generate_report_task
    job = generate_report_task.delay(user.tenant_id, req.report_type, req.period_days)
    return {"status": "generating", "job_id": str(job.id)}


@router.get("")
async def list_reports(
    report_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Reports stored as assets with type REPORT
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
            "url": r.url,
            "report_type": r.metadata_json.get("report_type"),
            "period": r.metadata_json.get("period"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


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
