from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
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

    # Get business name from Tenant (not on BusinessProfile)
    from app.models.tenant import Tenant
    tenant = await db.get(Tenant, str(user.tenant_id))
    biz_name = tenant.name if tenant else ""

    from app.services.creative_service import CreativeService
    svc = CreativeService(profile, business_name=biz_name)
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
    campaign_id: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Asset).where(Asset.tenant_id == user.tenant_id)
    if asset_type:
        query = query.where(Asset.asset_type == asset_type)
    if source:
        query = query.where(Asset.source == source)
    if campaign_id:
        # Filter by campaign_id stored in metadata_json
        query = query.where(
            Asset.metadata_json["campaign_id"].astext == campaign_id
        )
    if search:
        # Search in prompt or content
        query = query.where(
            sa.or_(
                Asset.content.ilike(f"%{search}%"),
                Asset.metadata_json["prompt"].astext.ilike(f"%{search}%"),
            )
        )

    # Count total for pagination
    from sqlalchemy import func
    count_query = query.with_only_columns(func.count()).order_by(None)
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(desc(Asset.created_at)).offset((page - 1) * limit).limit(limit)

    result = await db.execute(query)
    assets = result.scalars().all()
    return {
        "items": [
            {
                "id": a.id,
                "type": a.asset_type,
                "source": a.source,
                "url": a.url,
                "content": a.content,
                "metadata": a.metadata_json or {},
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in assets
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if limit else 1,
    }


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


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: str,
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete an asset by ID (must belong to user's tenant)."""
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.tenant_id == user.tenant_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    await db.delete(asset)
    await db.flush()
    return {"status": "deleted"}


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
            {"id": "google", "name": "Google Gemini", "description": "Google Nano Banana. Clean marketing visuals."},
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
        "google_ads_sizes": {
            "responsive_display": {"sizes": ["1200x628", "1024x1024", "1200x1200"], "description": "Responsive Display Ads"},
            "performance_max": {"sizes": ["1200x628", "1024x1024", "960x1200"], "description": "Performance Max campaigns"},
            "discovery": {"sizes": ["1200x628", "1024x1024", "960x1200"], "description": "Discovery/Demand Gen ads"},
            "youtube_thumbnail": {"sizes": ["1280x720"], "description": "YouTube video thumbnails"},
        },
    }


# ── GOOGLE ADS ASSET LIBRARY ──────────────────────────────────────

@router.get("/google-ads-assets")
async def list_google_ads_assets(
    asset_type: Optional[str] = Query(None, description="Filter: IMAGE, SITELINK, CALLOUT"),
    user: CurrentUser = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List existing assets in the connected Google Ads account."""
    from app.models.integration_google_ads import IntegrationGoogleAds
    from app.integrations.google_ads.client import GoogleAdsClient

    result = await db.execute(
        select(IntegrationGoogleAds).where(
            IntegrationGoogleAds.tenant_id == user.tenant_id,
            IntegrationGoogleAds.is_active == True,
        )
    )
    integration = result.scalar_one_or_none()
    if not integration or not integration.customer_id or integration.customer_id == "pending":
        return {"assets": [], "message": "No active Google Ads account connected"}

    client = GoogleAdsClient(
        customer_id=integration.customer_id,
        refresh_token_encrypted=integration.refresh_token_encrypted,
        login_customer_id=integration.login_customer_id,
    )

    types_filter = [asset_type] if asset_type else None
    assets = await client.list_assets(types_filter)
    return {"assets": assets, "total": len(assets)}


class SmartImageRequest(BaseModel):
    """Generate images optimized for a specific Google Ads placement."""
    campaign_id: Optional[str] = None
    ad_type: str = "responsive_display"  # responsive_display, performance_max, search_companion
    prompt: Optional[str] = None
    engine: str = "flux"
    style: str = "photorealistic"
    auto_upload_to_google: bool = False
    stability_model: str = "stable-image-ultra"
    flux_model: str = "flux-pro"
    google_model: str = "gemini-2.5-flash-image"


@router.post("/image/generate-for-ad")
async def generate_image_for_ad(
    req: SmartImageRequest,
    user: CurrentUser = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
):
    """Smart image generation — auto-detects sizes needed for ad type,
    generates prompt from campaign context, optionally uploads to Google Ads."""
    from app.integrations.image_generator.client import ImageGeneratorClient
    from app.models.integration_google_ads import IntegrationGoogleAds

    img_client = ImageGeneratorClient()
    if not img_client.is_configured:
        raise HTTPException(503, "Image generator not configured")

    # Load business context
    bp_result = await db.execute(
        select(BusinessProfile).where(BusinessProfile.tenant_id == user.tenant_id)
    )
    profile = bp_result.scalar_one_or_none()
    from app.models.tenant import Tenant
    tenant = await db.get(Tenant, str(user.tenant_id))
    biz_name = tenant.name if tenant else "Our Business"
    biz_type = profile.industry_classification if profile else "service"

    # Determine sizes based on ad type
    size_map = {
        "responsive_display": ["1792x1024", "1024x1024"],  # landscape + square
        "performance_max": ["1792x1024", "1024x1024", "1024x1792"],  # all 3
        "search_companion": ["1024x1024"],  # square only
        "discovery": ["1792x1024", "1024x1024"],
    }
    sizes = size_map.get(req.ad_type, ["1024x1024"])

    # Auto-generate prompt if not provided
    prompt = req.prompt
    if not prompt:
        # Try to get campaign context for better prompts
        campaign_name = ""
        if req.campaign_id:
            try:
                ads_result = await db.execute(
                    select(IntegrationGoogleAds).where(
                        IntegrationGoogleAds.tenant_id == user.tenant_id,
                        IntegrationGoogleAds.is_active == True,
                    )
                )
                integration = ads_result.scalar_one_or_none()
                if integration:
                    from app.integrations.google_ads.client import GoogleAdsClient
                    ads_client = GoogleAdsClient(
                        customer_id=integration.customer_id,
                        refresh_token_encrypted=integration.refresh_token_encrypted,
                        login_customer_id=integration.login_customer_id,
                    )
                    campaigns = await ads_client.get_campaigns()
                    camp = next((c for c in campaigns if str(c.get("id")) == req.campaign_id), None)
                    if camp:
                        campaign_name = camp.get("name", "")
            except Exception:
                pass

        prompt = (
            f"Professional {biz_type} business photo for Google Ads: "
            f"a certified {biz_type} technician from {biz_name} "
            f"{'performing ' + campaign_name.lower().split('|')[0].strip() + ' work' if campaign_name else 'providing expert service to a customer'}. "
            f"Clean branded uniform, professional equipment, well-lit setting. "
            f"Photorealistic, commercial quality, no text overlays, suitable for Google Ads."
        )

    metadata = {
        "businessName": biz_name,
        "businessType": biz_type,
        "description": f"Ad image for {biz_name}",
        "keywords": f"{biz_type}, professional, Google Ads",
    }

    # Generate one image per required size
    results = []
    for size in sizes:
        result = await img_client.generate_single(
            prompt=prompt,
            engine=req.engine,
            style=req.style,
            size=size,
            metadata=metadata,
            stability_model=req.stability_model,
            flux_model=req.flux_model,
            google_model=req.google_model,
        )
        if result.get("success"):
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
                    "size": size,
                    "prompt": prompt,
                    "ad_type": req.ad_type,
                    "status": "complete",
                    **metadata,
                },
            )
            db.add(asset)
            await db.flush()

            img_data = {
                "asset_id": asset.id,
                "image_url": result.get("image_url"),
                "size": size,
                "status": "complete",
            }

            # Optionally upload to Google Ads as an asset
            if req.auto_upload_to_google:
                try:
                    ads_result2 = await db.execute(
                        select(IntegrationGoogleAds).where(
                            IntegrationGoogleAds.tenant_id == user.tenant_id,
                            IntegrationGoogleAds.is_active == True,
                        )
                    )
                    integration2 = ads_result2.scalar_one_or_none()
                    if integration2:
                        from app.integrations.google_ads.client import GoogleAdsClient
                        ads_client2 = GoogleAdsClient(
                            customer_id=integration2.customer_id,
                            refresh_token_encrypted=integration2.refresh_token_encrypted,
                            login_customer_id=integration2.login_customer_id,
                        )
                        upload_result = await ads_client2.create_image_asset(
                            result.get("image_url"),
                            f"{biz_name} - {req.ad_type} - {size}",
                        )
                        if upload_result.get("status") == "success":
                            img_data["google_asset_resource"] = upload_result.get("asset_resource")
                except Exception as e:
                    img_data["google_upload_error"] = str(e)[:200]

            results.append(img_data)
        else:
            results.append({"size": size, "status": "failed", "error": result.get("error")})

    await db.commit()
    return {
        "ad_type": req.ad_type,
        "images": results,
        "prompt_used": prompt,
        "sizes_generated": len([r for r in results if r.get("status") == "complete"]),
    }
