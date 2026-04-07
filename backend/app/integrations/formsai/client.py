"""
FormsAI / BotForms Integration Client
======================================

Creates and manages contact forms for landing pages via the FormsAI API.
When a landing page is generated, this service:
1. Creates a hosted form with service-appropriate fields
2. Publishes the form to get an embeddable slug
3. Returns embed code for insertion into landing page HTML
4. Configures webhook to push submissions back to IntelliAds as leads

Flow:
  Landing Page Generated
    → FormsAI creates contact form
    → Form published with embed slug
    → Landing page HTML includes iframe embed
    → User submits form on landing page
    → FormsAI webhooks submission to IntelliAds
    → Lead appears in Calls & Leads dashboard
"""

import httpx
import structlog
from typing import Optional, Dict, Any, List

from app.core.config import settings

logger = structlog.get_logger()

# Default timeout
FORMSAI_TIMEOUT = 30.0


class FormsAIClient:
    """Client for FormsAI/BotForms API to create and manage contact forms."""

    def __init__(self):
        self.api_url = settings.FORMSAI_API_URL.rstrip("/")
        self.api_key = settings.FORMSAI_API_KEY
        self.embed_url = settings.FORMSAI_EMBED_URL.rstrip("/")
        self.available = bool(self.api_key and self.api_url)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=FORMSAI_TIMEOUT)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── PUBLIC API ──────────────────────────────────────────────

    async def create_landing_page_form(
        self,
        service: str,
        location: str,
        business_name: str = "",
        business_phone: str = "",
        business_email: str = "",
        notify_email: str = "",
        campaign_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a contact form for a landing page and return embed info.

        Returns:
        {
            "form_id": "...",
            "slug": "...",
            "endpoint": "...",
            "embed_iframe": "<iframe ...>",
            "embed_url": "https://botforms.ai/embed?slug=...",
            "share_url": "https://botforms.ai/f/...",
        }
        """
        if not self.available:
            logger.info("FormsAI not configured — skipping form creation")
            return None

        try:
            # Step 1: Create the form with a schema-based prompt
            form = await self._create_form(
                service=service,
                location=location,
                business_name=business_name,
                notify_email=notify_email or business_email,
            )
            if not form:
                return None

            form_id = form.get("id")
            if not form_id:
                return None

            # Step 2: Set the exact schema we want (override AI generation)
            schema = self._build_contact_schema(
                service=service,
                location=location,
                business_name=business_name,
                business_phone=business_phone,
            )
            await self._update_schema(form_id, schema)

            # Step 3: Configure webhook to push leads back to IntelliAds
            webhook_url = self._build_webhook_url(tenant_id, campaign_id)
            await self._update_form_settings(
                form_id,
                notify_email=notify_email or business_email,
                webhook_url=webhook_url,
            )

            # Step 4: Publish the form
            publish_result = await self._publish_form(form_id)
            if not publish_result:
                return None

            slug = publish_result.get("form", {}).get("shareSlug", "")
            endpoint = form.get("endpoint", "")

            return {
                "form_id": form_id,
                "slug": slug,
                "endpoint": endpoint,
                "embed_iframe": self._build_iframe(slug),
                "embed_url": f"{self.embed_url}/embed?slug={slug}",
                "share_url": f"{self.embed_url}/f/{slug}",
            }

        except Exception as e:
            logger.error("FormsAI form creation failed", error=str(e), service=service)
            return None
        finally:
            await self.close()

    # ── PRIVATE API CALLS ──────────────────────────────────────

    async def _create_form(
        self,
        service: str,
        location: str,
        business_name: str,
        notify_email: str,
    ) -> Optional[Dict]:
        """Generate a hosted form via FormsAI AI generation."""
        client = await self._get_client()

        prompt = (
            f"Create a professional contact form for a {service} business in {location}. "
            f"Include fields for: full name, email address, phone number, "
            f"service needed (dropdown with common {service} services), "
            f"preferred date and time, brief description of the issue or request. "
            f"Make it clean and conversion-optimized for Google Ads landing pages."
        )

        resp = await client.post(
            f"{self.api_url}/api/hosted-forms/generate",
            headers=self._headers(),
            json={
                "name": f"{business_name or service} - {location} Contact Form",
                "prompt": prompt,
            },
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("form")
        else:
            logger.warning("FormsAI create form failed",
                status=resp.status_code, body=resp.text[:300])
            return None

    async def _update_schema(self, form_id: str, schema: Dict) -> bool:
        """Override the AI-generated schema with our exact schema."""
        client = await self._get_client()

        resp = await client.put(
            f"{self.api_url}/api/hosted-forms/{form_id}/schema",
            headers=self._headers(),
            json={"schema": schema},
        )

        if resp.status_code == 200:
            return True
        logger.warning("FormsAI schema update failed",
            form_id=form_id, status=resp.status_code)
        return False

    async def _update_form_settings(
        self,
        form_id: str,
        notify_email: str = "",
        webhook_url: str = "",
    ) -> bool:
        """Update form notification and webhook settings."""
        client = await self._get_client()

        payload: Dict[str, Any] = {}
        if notify_email:
            payload["notifyEmail"] = notify_email
        if webhook_url:
            payload["webhookUrl"] = webhook_url

        if not payload:
            return True

        resp = await client.put(
            f"{self.api_url}/api/forms/{form_id}",
            headers=self._headers(),
            json=payload,
        )

        return resp.status_code == 200

    async def _publish_form(self, form_id: str) -> Optional[Dict]:
        """Publish the form to get embed codes and share URL."""
        client = await self._get_client()

        resp = await client.post(
            f"{self.api_url}/api/hosted-forms/{form_id}/publish",
            headers=self._headers(),
            json={},
        )

        if resp.status_code == 200:
            return resp.json()
        logger.warning("FormsAI publish failed",
            form_id=form_id, status=resp.status_code)
        return None

    # ── SCHEMA BUILDER ─────────────────────────────────────────

    def _build_contact_schema(
        self,
        service: str,
        location: str,
        business_name: str = "",
        business_phone: str = "",
    ) -> Dict:
        """Build a conversion-optimized contact form schema for the landing page."""
        return {
            "title": f"Get a Free {service} Quote",
            "description": f"Fill out the form below and we'll get back to you within minutes.",
            "sections": [
                {
                    "id": "contact_info",
                    "title": "Your Information",
                    "fields": [
                        {
                            "id": "full_name",
                            "key": "full_name",
                            "type": "name",
                            "label": "Full Name",
                            "placeholder": "Your full name",
                            "required": True,
                        },
                        {
                            "id": "phone",
                            "key": "phone",
                            "type": "phone",
                            "label": "Phone Number",
                            "placeholder": "(555) 123-4567",
                            "required": True,
                        },
                        {
                            "id": "email",
                            "key": "email",
                            "type": "email",
                            "label": "Email Address",
                            "placeholder": "you@example.com",
                            "required": False,
                        },
                    ],
                },
                {
                    "id": "service_details",
                    "title": "Service Details",
                    "fields": [
                        {
                            "id": "service_needed",
                            "key": "service_needed",
                            "type": "select",
                            "label": f"What {service} service do you need?",
                            "required": True,
                            "options": self._generate_service_options(service),
                        },
                        {
                            "id": "preferred_date",
                            "key": "preferred_date",
                            "type": "date",
                            "label": "Preferred Date",
                            "required": False,
                        },
                        {
                            "id": "description",
                            "key": "description",
                            "type": "textarea",
                            "label": "Describe your issue or request",
                            "placeholder": "Tell us about your situation so we can help...",
                            "required": False,
                        },
                    ],
                },
            ],
            "successMessage": f"Thank you! We'll contact you shortly. For immediate assistance, call {business_phone}." if business_phone else "Thank you! We'll contact you shortly.",
        }

    def _generate_service_options(self, service: str) -> List[str]:
        """Generate common service sub-options based on the service type."""
        service_lower = service.lower()

        # Common service categories with sub-options
        service_map = {
            "plumbing": ["Emergency Repair", "Drain Cleaning", "Water Heater", "Leak Detection", "Pipe Repair", "Sewer Line", "Fixture Installation", "Other"],
            "hvac": ["AC Repair", "Heating Repair", "AC Installation", "Furnace Installation", "Maintenance/Tune-Up", "Duct Cleaning", "Thermostat", "Other"],
            "electrical": ["Emergency Repair", "Panel Upgrade", "Wiring", "Lighting", "Outlet/Switch", "Generator", "EV Charger", "Other"],
            "roofing": ["Roof Repair", "Roof Replacement", "New Installation", "Inspection", "Leak Repair", "Gutter Service", "Storm Damage", "Other"],
            "pest control": ["General Pest", "Termites", "Rodents", "Bed Bugs", "Mosquitoes", "Wildlife", "Inspection", "Other"],
            "auto repair": ["Oil Change", "Brake Repair", "Engine Diagnostics", "Transmission", "Tire Service", "AC Repair", "Body Work", "Other"],
            "landscaping": ["Lawn Care", "Tree Service", "Landscape Design", "Irrigation", "Hardscaping", "Cleanup", "Maintenance Plan", "Other"],
            "cleaning": ["House Cleaning", "Deep Clean", "Move In/Out", "Commercial", "Carpet Cleaning", "Window Cleaning", "Post-Construction", "Other"],
        }

        # Try to match
        for key, options in service_map.items():
            if key in service_lower:
                return options

        # Generic fallback
        return [
            f"{service} - Repair",
            f"{service} - Installation",
            f"{service} - Maintenance",
            f"{service} - Inspection",
            f"{service} - Emergency",
            f"{service} - Consultation",
            "Other",
        ]

    # ── EMBED HELPERS ──────────────────────────────────────────

    def _build_iframe(self, slug: str, height: int = 650) -> str:
        """Generate iframe embed code for the form."""
        return (
            f'<iframe src="{self.embed_url}/embed?slug={slug}" '
            f'width="100%" height="{height}" frameborder="0" '
            f'loading="lazy" style="border:none;border-radius:12px;"></iframe>'
        )

    def _build_webhook_url(
        self,
        tenant_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> str:
        """Build the webhook URL that FormsAI will POST submissions to."""
        api_url = settings.API_URL.rstrip("/")
        webhook = f"{api_url}/api/leads/form-webhook"
        params = []
        if tenant_id:
            params.append(f"tenant_id={tenant_id}")
        if campaign_id:
            params.append(f"campaign_id={campaign_id}")
        if params:
            webhook += "?" + "&".join(params)
        return webhook


# Singleton
formsai_client = FormsAIClient()
