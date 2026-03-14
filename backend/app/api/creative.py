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
    prompt: Optional[str] = None
    service: Optional[str] = None
    engine: str = "dalle"
    style: str = "photorealistic"
    size: str = "1024x1024"
    metadata: Optional[Dict[str, Any]] = None


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
    variants = await svc.generate_ad_copy(
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
    from app.integrations.image_generator.client import ImageGeneratorClient

    # Load business profile for auto-metadata
    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = bp_result.scalar_one_or_none()

    client = ImageGeneratorClient()
    if not client.is_configured:
        raise HTTPException(status_code=503, detail="Image generator not configured. Set IMAGE_GENERATOR_API_URL.")

    # Get business name from Tenant (not on BusinessProfile)
    from app.models.tenant import Tenant
    tenant = await db.get(Tenant, str(user.tenant_id))
    biz_name = tenant.name if tenant else "Our Business"

    # If no prompt provided, auto-generate one from service + profile
    if req.prompt:
        prompt = req.prompt
        metadata = req.metadata or {}
    else:
        service = req.service or "service"
        biz_type = profile.industry_classification if profile else "service"
        city = ""
        state = ""
        if profile and profile.locations_json:
            locs = profile.locations_json if isinstance(profile.locations_json, list) else profile.locations_json.get("cities", [])
            if locs:
                loc = locs[0] if isinstance(locs[0], str) else locs[0].get("name", "")
                city = loc

        prompt = (
            f"Professional {biz_type} business photo: a licensed {service} expert "
            f"performing {service} work for a customer. "
            f"Clean uniform, professional tools, well-lit workspace. "
            f"Photorealistic, high quality, suitable for Google Ads."
        )
        metadata = {
            "businessName": biz_name,
            "businessType": biz_type,
            "city": city,
            "state": state,
            "description": f"Professional {service} by {biz_name} in {city}",
            "keywords": f"{service}, {biz_type}, {city}, professional, licensed",
        }

    result = await client.generate_single(
        prompt=prompt,
        engine=req.engine,
        style=req.style,
        size=req.size,
        metadata=metadata,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Image generation failed"))

    # Save to asset library
    asset = Asset(
        tenant_id=user.tenant_id,
        asset_type="IMAGE",
        source="ai_image_generator",
        url=result.get("image_url"),
        metadata_json={
            "filename": result.get("filename"),
            "engine": req.engine,
            "style": req.style,
            "prompt": prompt,
            "status": "complete",
            **metadata,
        },
    )
    db.add(asset)
    await db.flush()

    return {
        "asset_id": asset.id,
        "image_url": result.get("image_url"),
        "filename": result.get("filename"),
        "status": "complete",
    }


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
        return {"status": "complete", "url": asset.url, "metadata": asset.metadata_json}

    return {"status": "unknown"}


@router.get("/image/health")
async def image_generator_health():
    from app.integrations.image_generator.client import ImageGeneratorClient
    client = ImageGeneratorClient()
    return await client.health_check()


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


class DeployAdCopyRequest(BaseModel):
    account_id: str
    ad_group_id: str
    campaign_id: str
    headlines: List[str]
    descriptions: List[str]
    final_url: str


@router.post("/copy/deploy")
async def deploy_ad_copy(
    req: DeployAdCopyRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Deploy AI-generated ad copy as a Responsive Search Ad in Google Ads."""
    from app.models.ads_account_cache import AdsAccountCache
    from app.models.integration_google_ads import IntegrationGoogleAds

    # Look up account
    acct = await db.execute(
        select(AdsAccountCache).where(
            AdsAccountCache.id == req.account_id,
            AdsAccountCache.tenant_id == user.tenant_id,
        )
    )
    account = acct.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    integration = await db.execute(
        select(IntegrationGoogleAds).where(IntegrationGoogleAds.tenant_id == user.tenant_id)
    )
    ig = integration.scalar_one_or_none()
    if not ig:
        raise HTTPException(status_code=400, detail="Google Ads not connected")

    from app.integrations.google_ads.client import GoogleAdsClient
    gads = GoogleAdsClient(
        customer_id=account.customer_id,
        refresh_token_encrypted=ig.refresh_token_encrypted,
        login_customer_id=ig.login_customer_id,
    )

    ad_group_resource = f"customers/{account.customer_id}/adGroups/{req.ad_group_id}"
    result = await gads.create_responsive_search_ad(
        ad_group_resource=ad_group_resource,
        ad_data={
            "headlines": req.headlines[:15],
            "descriptions": req.descriptions[:4],
            "final_urls": [req.final_url],
        },
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to create ad"))

    return {
        "status": "deployed",
        "ad_resource": result.get("ad_resource"),
        "headlines_count": len(req.headlines[:15]),
        "descriptions_count": len(req.descriptions[:4]),
    }


@router.get("/templates")
async def list_image_templates():
    return {
        "engines": [
            {"id": "dalle", "name": "DALL-E 3", "description": "OpenAI's best image model. Great quality, $0.04/image."},
            {"id": "stability", "name": "Stability AI", "description": "Stable Diffusion Ultra. Photorealistic, fast."},
            {"id": "flux", "name": "Flux.1", "description": "Fal.ai Flux Pro. High detail, artistic flexibility."},
        ],
        "styles": [
            {"id": "photorealistic", "name": "Photorealistic", "description": "Professional photography look — best for Google Ads"},
            {"id": "cartoon", "name": "Cartoon", "description": "Colorful illustrated style"},
            {"id": "artistic", "name": "Artistic", "description": "Oil painting / fine art style"},
            {"id": "none", "name": "No Enhancement", "description": "Raw prompt — no style enhancement applied"},
        ],
        "sizes": [
            {"id": "1024x1024", "name": "Square (1024x1024)", "description": "Google Display, social media"},
            {"id": "1792x1024", "name": "Landscape (1792x1024)", "description": "Banner ads, YouTube thumbnails"},
            {"id": "1024x1792", "name": "Portrait (1024x1792)", "description": "Stories, vertical display"},
        ],
        "prompt_templates": [
            {"id": "locksmith_emergency", "name": "Locksmith Emergency", "prompt": "Professional locksmith responding to emergency lockout, arriving at customer front door with toolkit, nighttime scene with porch light, realistic and professional"},
            {"id": "locksmith_auto", "name": "Auto Locksmith", "prompt": "Licensed automotive locksmith programming a car key fob next to a modern car, professional uniform, specialized equipment, dealership quality service"},
            {"id": "locksmith_rekey", "name": "Lock Rekey Service", "prompt": "Locksmith technician rekeying a residential deadbolt lock, close-up of hands working with precision tools, clean professional workspace"},
            {"id": "plumber_emergency", "name": "Emergency Plumber", "prompt": "Professional plumber fixing a burst pipe under a kitchen sink, water being contained, heroic service moment, professional tools and uniform"},
            {"id": "hvac_repair", "name": "HVAC Repair", "prompt": "HVAC technician servicing an air conditioning unit on a rooftop, professional uniform, diagnostic tools, clear blue sky, reliable service"},
            {"id": "roofer_inspection", "name": "Roof Inspection", "prompt": "Professional roofer inspecting shingles on a residential roof, safety harness, clipboard, clear day, trustworthy and thorough inspection"},
            {"id": "generic_trust", "name": "Trust & Team", "prompt": "Small business service team posing confidently in front of branded company vehicle, uniforms, friendly professional appearance, trust and reliability"},
        ],
    }
