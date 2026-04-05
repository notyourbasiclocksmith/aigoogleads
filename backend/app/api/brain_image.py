"""
Brain API — Image generation endpoints for Jarvis S2S calls.
Wraps the existing ImageGeneratorClient (SEOpix DALLE/Stability/Flux).
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_brain_api_key, S2SContext
from app.integrations.image_generator.client import ImageGeneratorClient

router = APIRouter(prefix="/images")


@router.get("/health")
async def image_health(
    ctx: S2SContext = Depends(require_brain_api_key),
):
    client = ImageGeneratorClient()
    return {
        "status": "healthy" if client.is_configured else "not_configured",
        "engines": ["dalle", "stability", "flux"],
    }


@router.post("/generate")
async def generate_image(
    prompt: str = Query(..., description="Image generation prompt"),
    engine: str = Query("dalle", description="dalle, stability, or flux"),
    style: str = Query("photorealistic"),
    size: str = Query("1024x1024"),
    ctx: S2SContext = Depends(require_brain_api_key),
):
    """Generate an image from a text prompt."""
    client = ImageGeneratorClient()
    if not client.is_configured:
        return {"error": "Image generator not configured"}
    result = await client.generate_single(
        prompt=prompt, engine=engine, style=style, size=size,
    )
    return result


@router.post("/generate-ad")
async def generate_ad_image(
    service: str = Query(..., description="Service or product being advertised"),
    business_name: str = Query(""),
    business_type: str = Query(""),
    engine: str = Query("dalle"),
    style: str = Query("photorealistic"),
    size: str = Query("1024x1024"),
    ctx: S2SContext = Depends(require_brain_api_key),
):
    """Generate an ad-specific image using AI prompt engineering."""
    client = ImageGeneratorClient()
    if not client.is_configured:
        return {"error": "Image generator not configured"}
    result = await client.generate_ad_image(
        service=service,
        business_name=business_name,
        business_type=business_type,
        engine=engine,
        style=style,
        size=size,
    )
    return result


@router.post("/generate-social")
async def generate_social_image(
    topic: str = Query(..., description="Post topic"),
    platform: str = Query("instagram", description="instagram, facebook, google"),
    business_name: str = Query(""),
    engine: str = Query("dalle"),
    ctx: S2SContext = Depends(require_brain_api_key),
):
    """Generate a social-media-optimized image."""
    size_map = {
        "instagram": "1080x1080",
        "facebook": "1200x630",
        "google": "1024x1024",
    }
    size = size_map.get(platform, "1024x1024")

    client = ImageGeneratorClient()
    if not client.is_configured:
        return {"error": "Image generator not configured"}

    prompt = f"Professional social media post image for {platform}. Topic: {topic}."
    if business_name:
        prompt += f" Business: {business_name}."
    prompt += " Clean, modern, eye-catching, no text overlay."

    result = await client.generate_single(
        prompt=prompt, engine=engine, style="photorealistic", size=size,
    )
    result["platform"] = platform
    result["recommended_size"] = size
    return result
