"""
AI Image Generator Client — Calls the SEOpix Flask API
(C:\06725 prelaunch\ai-image-generator) to generate ad images.

Supports 3 engines: DALL-E 3, Stability AI, Flux.1
Features: SEO filenames, EXIF metadata, GPS geo-tagging, Cloudinary storage
"""
from typing import Dict, Any, Optional, List
import httpx
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class ImageGeneratorClient:
    def __init__(self):
        self.base_url = settings.IMAGE_GENERATOR_API_URL.rstrip("/") if settings.IMAGE_GENERATOR_API_URL else ""
        self.api_key = settings.IMAGE_GENERATOR_API_KEY
        self.timeout = 120.0  # Image generation can take 30-60s

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def generate_single(
        self,
        prompt: str,
        engine: str = "dalle",
        style: str = "photorealistic",
        size: str = "1024x1024",
        metadata: Optional[Dict[str, Any]] = None,
        stability_model: str = "stable-image-ultra",
        flux_model: str = "flux-pro",
        google_model: str = "gemini-2.5-flash-image",
    ) -> Dict[str, Any]:
        """
        Generate a single image via the SEOpix Next.js API.

        Args:
            prompt: Image description prompt
            engine: 'dalle', 'stability', 'flux', or 'google'
            style: 'photorealistic', 'cartoon', 'artistic', or 'none'
            size: '1024x1024', '1792x1024', or '1024x1792'
            metadata: SEO metadata dict with businessName, businessType, city, state,
                      description, keywords, latitude, longitude
            stability_model: 'stable-image-ultra', 'sd3.5-large', 'sd3.5-large-turbo', 'sd3.5-medium'
            flux_model: 'flux-pro' or 'flux-dev'
            google_model: 'gemini-2.5-flash-image', 'gemini-3.1-flash-image-preview', 'gemini-3-pro-image-preview'

        Returns:
            dict with success, filename, imageUrl
        """
        if not self.is_configured:
            return {"error": "IMAGE_GENERATOR_API_URL not configured", "success": False}

        payload = {
            "prompt": prompt,
            "engine": engine,
            "style": style,
            "size": size,
            "metadata": metadata or {},
            "stabilityModel": stability_model,
            "fluxModel": flux_model,
            "googleModel": google_model,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate-single",
                    json=payload,
                    headers=self._headers(),
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info("Image generated", filename=data.get("filename"), engine=engine)
                    return {
                        "success": True,
                        "filename": data.get("filename"),
                        "image_url": data.get("imageUrl"),
                        "message": data.get("message", ""),
                    }
                else:
                    error = resp.json().get("error", resp.text[:200]) if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:200]
                    error_lower = error.lower() if isinstance(error, str) else ""

                    # Auto-fallback: if Google engine fails with location error, retry with DALL-E
                    if engine == "google" and "location" in error_lower and "not supported" in error_lower:
                        logger.warning("Google image gen location not supported — falling back to DALL-E",
                            original_error=error[:100])
                        fallback_payload = {**payload, "engine": "dalle"}
                        fallback_payload.pop("googleModel", None)
                        fb_resp = await client.post(
                            f"{self.base_url}/api/generate-single",
                            json=fallback_payload,
                            headers=self._headers(),
                        )
                        if fb_resp.status_code in (200, 201):
                            data = fb_resp.json()
                            logger.info("Fallback DALL-E image generated", filename=data.get("filename"))
                            return {
                                "success": True,
                                "filename": data.get("filename"),
                                "image_url": data.get("imageUrl"),
                                "message": "Generated with DALL-E fallback (Google location not supported)",
                                "fallback_engine": "dalle",
                            }
                        else:
                            fb_error = fb_resp.text[:200]
                            logger.error("DALL-E fallback also failed", error=fb_error)

                    logger.error("Image generation failed", status=resp.status_code, error=error)
                    return {"success": False, "error": error}

        except httpx.TimeoutException:
            logger.error("Image generation timed out", engine=engine)
            return {"success": False, "error": "Image generation timed out. Try again."}
        except Exception as e:
            logger.error("Image generation exception", error=str(e))
            return {"success": False, "error": str(e)}

    async def generate_batch(
        self,
        prompt: str,
        engine: str = "dalle",
        style: str = "photorealistic",
        size: str = "1024x1024",
        metadata: Optional[Dict[str, Any]] = None,
        stability_model: str = "stable-image-ultra",
        flux_model: str = "flux-pro",
    ) -> Dict[str, Any]:
        """
        Generate 3 images at once (batch mode) via the SEOpix Flask API.

        Returns:
            dict with success, images list [{filename, imageUrl}], count
        """
        if not self.is_configured:
            return {"error": "IMAGE_GENERATOR_API_URL not configured", "success": False}

        payload = {
            "prompt": prompt,
            "engine": engine,
            "style": style,
            "size": size,
            "metadata": metadata or {},
            "stabilityModel": stability_model,
            "fluxModel": flux_model,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout * 3) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate-batch",
                    json=payload,
                    headers=self._headers(),
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    images = data.get("images", [])
                    logger.info("Batch images generated", count=len(images), engine=engine)
                    return {
                        "success": True,
                        "images": [
                            {"filename": img.get("filename"), "image_url": img.get("imageUrl")}
                            for img in images
                        ],
                        "count": data.get("count", len(images)),
                    }
                else:
                    error = resp.json().get("error", resp.text[:200]) if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:200]
                    logger.error("Batch generation failed", status=resp.status_code, error=error)
                    return {"success": False, "error": error}

        except httpx.TimeoutException:
            logger.error("Batch generation timed out", engine=engine)
            return {"success": False, "error": "Batch generation timed out."}
        except Exception as e:
            logger.error("Batch generation exception", error=str(e))
            return {"success": False, "error": str(e)}

    async def generate_ad_image(
        self,
        service: str,
        business_name: str,
        business_type: str,
        city: str = "",
        state: str = "",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        engine: str = "dalle",
        style: str = "photorealistic",
        size: str = "1024x1024",
    ) -> Dict[str, Any]:
        """
        High-level method: generate an ad-ready image for a specific service.
        Builds an optimized prompt and metadata automatically.

        Engine fallback order: requested engine -> dalle -> placeholder.
        """
        prompt = (
            f"Professional {business_type} business photo: a licensed {service.lower()} expert "
            f"performing {service.lower()} work for a customer. "
            f"Clean uniform, professional tools, well-lit workspace. "
            f"Photorealistic, high quality, suitable for Google Ads."
        )

        metadata = {
            "businessName": business_name,
            "businessType": business_type,
            "city": city,
            "state": state,
            "description": f"Professional {service} by {business_name} in {city}, {state}",
            "keywords": f"{service}, {business_type}, {city}, {state}, professional, licensed, insured",
        }
        if latitude is not None:
            metadata["latitude"] = str(latitude)
        if longitude is not None:
            metadata["longitude"] = str(longitude)

        # DALL-E only supports 1024x1024, 1024x1792, 1792x1024
        # Normalize any non-standard size to the closest DALL-E landscape
        _DALLE_SIZES = {"1024x1024", "1024x1792", "1792x1024"}
        dalle_safe_size = size if size in _DALLE_SIZES else "1792x1024"

        result = await self.generate_single(
            prompt=prompt,
            engine=engine,
            style=style,
            size=dalle_safe_size if engine == "dalle" else size,
            metadata=metadata,
        )

        # If primary engine failed and it was not already dalle, try dalle as fallback
        if not result.get("success") and engine != "dalle":
            logger.warning("Primary engine failed, trying DALL-E fallback",
                original_engine=engine, error=result.get("error", "")[:100])
            result = await self.generate_single(
                prompt=prompt,
                engine="dalle",
                style=style,
                size=dalle_safe_size,
                metadata=metadata,
            )

        # If all engines failed, return a placeholder image URL
        if not result.get("success"):
            logger.warning("All image engines failed — returning placeholder",
                service=service, error=result.get("error", "")[:100])
            # Unsplash Source provides royalty-free placeholder images by keyword
            placeholder_query = f"{business_type}+{service}+professional".replace(" ", "+")
            w, h = size.split("x") if "x" in size else ("1024", "1024")
            result = {
                "success": True,
                "image_url": f"https://source.unsplash.com/{w}x{h}/?{placeholder_query}",
                "filename": f"placeholder-{service.lower().replace(' ', '-')}.jpg",
                "message": "Placeholder image (all generation engines unavailable)",
                "is_placeholder": True,
            }

        return result

    async def health_check(self) -> Dict[str, Any]:
        """Check if the image generator API is healthy."""
        if not self.is_configured:
            return {"status": "not_configured", "url": ""}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/health", headers=self._headers())
                if resp.status_code == 200:
                    return {"status": "healthy", "url": self.base_url, **resp.json()}
                return {"status": "unhealthy", "url": self.base_url, "code": resp.status_code}
        except Exception as e:
            return {"status": "error", "url": self.base_url, "error": str(e)}
