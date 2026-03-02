"""
seopix.ai Adapter — Image generation for ad creatives.

Interface:
- submit_image_job(template, business_name, service, colors, text_overlay)
- check_job_status(job_id)
- list_templates()
"""
from typing import Dict, Any, Optional
import httpx
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class SeopixClient:
    def __init__(self):
        self.base_url = settings.SEOPIX_API_URL
        self.api_key = settings.SEOPIX_API_KEY
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def submit_image_job(
        self,
        template: str,
        business_name: Optional[str] = None,
        service: Optional[str] = None,
        colors: Optional[Dict[str, str]] = None,
        text_overlay: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "template": template,
            "params": {
                "business_name": business_name or "",
                "service": service or "",
                "colors": colors or {},
                "text_overlay": text_overlay or "",
            },
            "output_format": "png",
            "dimensions": {"width": 1200, "height": 628},
        }

        try:
            resp = await self.client.post(f"{self.base_url}/jobs", json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                logger.info("seopix job submitted", job_id=data.get("job_id"))
                return {
                    "job_id": data.get("job_id", data.get("id")),
                    "status": data.get("status", "processing"),
                }
            else:
                logger.error("seopix submit failed", status=resp.status_code, body=resp.text[:200])
                return {"job_id": None, "status": "error", "error": resp.text[:200]}
        except Exception as e:
            logger.error("seopix submit exception", error=str(e))
            return {"job_id": None, "status": "error", "error": str(e)}

    async def check_job_status(self, job_id: str) -> Dict[str, Any]:
        try:
            resp = await self.client.get(f"{self.base_url}/jobs/{job_id}")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "job_id": job_id,
                    "status": data.get("status", "processing"),
                    "url": data.get("url") or data.get("output_url"),
                    "metadata": data.get("metadata", {}),
                }
            else:
                return {"job_id": job_id, "status": "error", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.error("seopix status check failed", job_id=job_id, error=str(e))
            return {"job_id": job_id, "status": "error", "error": str(e)}

    async def list_templates(self) -> list:
        try:
            resp = await self.client.get(f"{self.base_url}/templates")
            if resp.status_code == 200:
                return resp.json().get("templates", [])
            return []
        except Exception:
            return []

    async def close(self):
        await self.client.aclose()
