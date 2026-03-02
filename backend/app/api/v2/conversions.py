"""Module 2 — Conversion Truth Layer API Routes (GA4, GTM, Offline, Profit)"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.v2.integration_ga4 import IntegrationGA4
from app.models.v2.tracking_health_report import TrackingHealthReport
from app.models.v2.offline_conversion import OfflineConversion
from app.models.v2.offline_conversion_upload import OfflineConversionUpload
from app.services.v2.profit_model import get_profit_targets, update_profit_model

router = APIRouter()


# ── GA4 ──
class GA4ConnectRequest(BaseModel):
    tenant_id: str
    property_id: str
    refresh_token: Optional[str] = None


@router.post("/ga4/connect")
async def connect_ga4(req: GA4ConnectRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(IntegrationGA4).where(IntegrationGA4.tenant_id == req.tenant_id)
    )
    ga4 = existing.scalars().first()
    if ga4:
        ga4.property_id = req.property_id
        if req.refresh_token:
            ga4.refresh_token_encrypted = req.refresh_token  # In prod: encrypt
    else:
        ga4 = IntegrationGA4(
            id=str(uuid.uuid4()),
            tenant_id=req.tenant_id,
            property_id=req.property_id,
            refresh_token_encrypted=req.refresh_token or "",
        )
        db.add(ga4)
    return {"connected": True, "property_id": req.property_id}


@router.post("/ga4/sync")
async def sync_ga4(tenant_id: str, db: AsyncSession = Depends(get_db)):
    """Trigger GA4 data sync. Stub — real impl calls GA4 Data API."""
    stmt = select(IntegrationGA4).where(IntegrationGA4.tenant_id == tenant_id)
    result = await db.execute(stmt)
    ga4 = result.scalars().first()
    if not ga4:
        raise HTTPException(404, "GA4 integration not found")
    ga4.last_sync_at = datetime.now(timezone.utc)
    return {"synced": True, "property_id": ga4.property_id, "stub": True}


@router.get("/ga4/status")
async def ga4_status(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(IntegrationGA4).where(IntegrationGA4.tenant_id == tenant_id)
    result = await db.execute(stmt)
    ga4 = result.scalars().first()
    if not ga4:
        return {"connected": False}
    return {
        "connected": True,
        "property_id": ga4.property_id,
        "last_sync_at": ga4.last_sync_at.isoformat() if ga4.last_sync_at else None,
    }


# ── Tracking Health ──
@router.post("/tracking/health/run")
async def run_tracking_health(tenant_id: str, db: AsyncSession = Depends(get_db)):
    """Run tracking health check on tenant's website. Stub."""
    report = TrackingHealthReport(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        source="site_scan",
        report_json={
            "checks": [
                {"name": "gtag.js presence", "status": "pass", "detail": "Google tag detected"},
                {"name": "GTM container", "status": "pass", "detail": "GTM-XXXXXXX found"},
                {"name": "Conversion tag", "status": "warn", "detail": "No conversion linker tag detected"},
                {"name": "Enhanced conversions", "status": "info", "detail": "Not configured"},
            ],
            "overall_score": 75,
            "recommendations": ["Add conversion linker tag", "Consider enabling enhanced conversions"],
        },
    )
    db.add(report)
    return report.report_json


@router.get("/tracking/health")
async def get_tracking_health(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(TrackingHealthReport)
        .where(TrackingHealthReport.tenant_id == tenant_id)
        .order_by(TrackingHealthReport.created_at.desc())
        .limit(5)
    )
    result = await db.execute(stmt)
    reports = result.scalars().all()
    return [
        {"id": r.id, "source": r.source, "report": r.report_json, "created_at": r.created_at.isoformat()}
        for r in reports
    ]


# ── Offline Conversions ──
class OfflineConversionEntry(BaseModel):
    gclid: str
    conversion_name: str
    conversion_time: str
    value: Optional[float] = None
    currency: str = "USD"


class OfflineUploadRequest(BaseModel):
    tenant_id: str
    google_customer_id: str
    conversions: List[OfflineConversionEntry]


class FieldMappingRequest(BaseModel):
    tenant_id: str
    upload_id: str
    mappings: dict  # {"csv_col": "field_name", ...}


@router.post("/offline-conversions/upload")
async def upload_offline_conversions(req: OfflineUploadRequest, db: AsyncSession = Depends(get_db)):
    upload = OfflineConversionUpload(
        id=str(uuid.uuid4()),
        tenant_id=req.tenant_id,
        row_count=len(req.conversions),
        status="processing",
    )
    db.add(upload)

    success = 0
    errors = 0
    for entry in req.conversions:
        try:
            conv_time = datetime.fromisoformat(entry.conversion_time)
        except ValueError:
            errors += 1
            continue

        conv = OfflineConversion(
            id=str(uuid.uuid4()),
            tenant_id=req.tenant_id,
            google_customer_id=req.google_customer_id,
            gclid=entry.gclid,
            conversion_name=entry.conversion_name,
            conversion_time=conv_time,
            value=entry.value,
            currency=entry.currency,
            status="pending",
            upload_id=upload.id,
        )
        db.add(conv)
        success += 1

    upload.success_count = success
    upload.error_count = errors
    upload.status = "completed"
    upload.results_json = {"success": success, "errors": errors}

    return {"upload_id": upload.id, "success": success, "errors": errors}


@router.post("/offline-conversions/map-fields")
async def map_fields(req: FieldMappingRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(OfflineConversionUpload).where(OfflineConversionUpload.id == req.upload_id)
    result = await db.execute(stmt)
    upload = result.scalars().first()
    if not upload:
        raise HTTPException(404, "Upload not found")
    upload.mapped_fields_json = req.mappings
    return {"mapped": True, "upload_id": req.upload_id}


@router.get("/offline-conversions/uploads")
async def list_uploads(tenant_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(OfflineConversionUpload)
        .where(OfflineConversionUpload.tenant_id == tenant_id)
        .order_by(OfflineConversionUpload.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    uploads = result.scalars().all()
    return [
        {
            "id": u.id, "status": u.status, "row_count": u.row_count,
            "success_count": u.success_count, "error_count": u.error_count,
            "created_at": u.created_at.isoformat(),
        }
        for u in uploads
    ]


# ── Profit Model ──
class ProfitModelUpdateRequest(BaseModel):
    tenant_id: str
    avg_job_value: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    close_rate_estimate: Optional[float] = None
    refund_rate_estimate: Optional[float] = None
    desired_profit_buffer_pct: Optional[float] = None


@router.get("/profit-model")
async def get_profit_model(tenant_id: str, db: AsyncSession = Depends(get_db)):
    return await get_profit_targets(db, tenant_id)


@router.put("/profit-model")
async def update_profit_model_endpoint(req: ProfitModelUpdateRequest, db: AsyncSession = Depends(get_db)):
    return await update_profit_model(
        db, req.tenant_id,
        avg_job_value=req.avg_job_value,
        gross_margin_pct=req.gross_margin_pct,
        close_rate_estimate=req.close_rate_estimate,
        refund_rate_estimate=req.refund_rate_estimate,
        desired_profit_buffer_pct=req.desired_profit_buffer_pct,
    )
