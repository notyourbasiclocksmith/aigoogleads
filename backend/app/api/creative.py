from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.database import get_db
from app.core.deps import require_tenant, require_analyst, CurrentUser
from app.models.asset import Asset
from app.models.business_profile import BusinessProfile

router = APIRouter()


class GenerateCopyRequest(BaseModel):
    service: Optional[str] = None
    location: Optional[str] = None
    offer: Optional[str] = None
    tone: Optional[str] = None
    count: int = 10


class GenerateImageRequest(BaseModel):
    template: str
    business_name: Optional[str] = None
    service: Optional[str] = None
    colors: Optional[Dict[str, str]] = None
    text_overlay: Optional[str] = None


class SaveAssetRequest(BaseModel):
    asset_type: str
    content: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = {}


@router.post("/copy/generate")
async def generate_copy(
    req: GenerateCopyRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = result.scalar_one_or_none()

    from app.services.creative_service import CreativeService
    svc = CreativeService(profile)
    variants = svc.generate_ad_copy(
        service=req.service,
        location=req.location,
        offer=req.offer,
        tone=req.tone,
        count=req.count,
    )
    return variants


@router.post("/image/generate")
async def generate_image(
    req: GenerateImageRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    from app.integrations.seopix.client import SeopixClient
    client = SeopixClient()
    job = await client.submit_image_job(
        template=req.template,
        business_name=req.business_name,
        service=req.service,
        colors=req.colors,
        text_overlay=req.text_overlay,
    )

    asset = Asset(
        tenant_id=user.tenant_id,
        asset_type="IMAGE",
        source="seopix",
        seopix_job_id=job.get("job_id"),
        metadata_json={"template": req.template, "status": "processing"},
    )
    db.add(asset)
    await db.flush()

    return {"asset_id": asset.id, "job_id": job.get("job_id"), "status": "processing"}


@router.get("/image/{asset_id}/status")
async def check_image_status(
    asset_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.tenant_id == user.tenant_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset.url:
        return {"status": "complete", "url": asset.url}

    if asset.seopix_job_id:
        from app.integrations.seopix.client import SeopixClient
        client = SeopixClient()
        status = await client.check_job_status(asset.seopix_job_id)
        if status.get("status") == "complete":
            asset.url = status.get("url")
            asset.metadata_json = {**asset.metadata_json, "status": "complete"}
            await db.flush()
            return {"status": "complete", "url": asset.url}
        return {"status": status.get("status", "processing")}

    return {"status": "unknown"}


@router.get("/assets")
async def list_assets(
    asset_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Asset).where(Asset.tenant_id == user.tenant_id)
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    query = query.order_by(desc(Asset.created_at)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    assets = result.scalars().all()
    return [
        {
            "id": a.id,
            "type": a.asset_type,
            "source": a.source,
            "url": a.url,
            "content": a.content,
            "metadata": a.metadata_json,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in assets
    ]


@router.post("/assets")
async def save_asset(
    req: SaveAssetRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    asset = Asset(
        tenant_id=user.tenant_id,
        asset_type=req.asset_type,
        source="manual",
        content=req.content,
        url=req.url,
        metadata_json=req.metadata,
    )
    db.add(asset)
    await db.flush()
    return {"id": asset.id, "status": "saved"}


@router.get("/templates")
async def list_image_templates():
    return {
        "templates": [
            {"id": "locksmith_emergency", "name": "Locksmith Emergency", "description": "Emergency locksmith service image with urgency theme"},
            {"id": "locksmith_premium", "name": "Premium Automotive Locksmith", "description": "Professional automotive locksmith image"},
            {"id": "roofer_storm", "name": "Roofer Storm Damage", "description": "Storm damage roof repair image"},
            {"id": "mechanic_diagnostics", "name": "Mechanic Diagnostics", "description": "Auto mechanic diagnostics image"},
            {"id": "hvac_seasonal", "name": "HVAC Seasonal", "description": "Seasonal HVAC service image"},
            {"id": "plumber_emergency", "name": "Plumber Emergency", "description": "Emergency plumbing service image"},
            {"id": "generic_service", "name": "Generic Service", "description": "General service business image"},
        ]
    }
