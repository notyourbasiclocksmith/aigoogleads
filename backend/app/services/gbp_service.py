"""
Google Business Profile Service.
Fetches location details, reviews, hours, rating from GBP API.
Auto-populates BusinessProfile structured fields.

Uses the Business Profile API v1:
  - https://mybusinessbusinessinformation.googleapis.com/v1/
  - https://mybusinessaccountmanagement.googleapis.com/v1/
"""
import structlog
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_profile import BusinessProfile
from app.models.gbp_connection import GBPConnection
from app.models.gbp_location import GBPLocation
from app.models.gbp_post import GBPReview
from app.services import gbp_oauth_service

logger = structlog.get_logger()

# API base URLs
ACCOUNT_MGMT_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"
BIZ_INFO_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
GBP_API_BASE = "https://mybusiness.googleapis.com/v4"


class GBPService:
    """Interact with Google Business Profile APIs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Account & Location Discovery ────────────────────────────────

    async def list_accounts(self, tenant_id: str) -> List[Dict]:
        """List GBP accounts accessible by the authenticated user."""
        creds = await gbp_oauth_service.get_credentials(tenant_id, self.db)
        if not creds:
            return []

        headers = {"Authorization": f"Bearer {creds.token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{ACCOUNT_MGMT_BASE}/accounts", headers=headers)
            if resp.status_code != 200:
                logger.warning("GBP list_accounts failed", status=resp.status_code, body=resp.text[:300])
                return []
            data = resp.json()
        return data.get("accounts", [])

    async def list_locations(self, tenant_id: str, account_name: str) -> List[Dict]:
        """List locations for a GBP account."""
        creds = await gbp_oauth_service.get_credentials(tenant_id, self.db)
        if not creds:
            return []

        headers = {"Authorization": f"Bearer {creds.token}"}
        url = f"{BIZ_INFO_BASE}/{account_name}/locations?readMask=name,title,phoneNumbers,storefrontAddress,websiteUri,regularHours,specialHours,categories,metadata,serviceArea,profile,moreHours"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("GBP list_locations failed", status=resp.status_code, body=resp.text[:300])
                return []
            data = resp.json()
        return data.get("locations", [])

    # ── Fetch Full Location Detail ──────────────────────────────────

    async def fetch_location_detail(self, tenant_id: str, location_name: str) -> Optional[Dict]:
        """Fetch full details for a single GBP location."""
        creds = await gbp_oauth_service.get_credentials(tenant_id, self.db)
        if not creds:
            return None

        headers = {"Authorization": f"Bearer {creds.token}"}
        url = f"{BIZ_INFO_BASE}/{location_name}?readMask=name,title,phoneNumbers,storefrontAddress,websiteUri,regularHours,specialHours,categories,metadata,serviceArea,profile"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("GBP fetch_location failed", status=resp.status_code, body=resp.text[:300])
                return None
            return resp.json()

    # ── Reviews ─────────────────────────────────────────────────────

    async def fetch_reviews(self, tenant_id: str, location_name: str, page_size: int = 50) -> Dict:
        """Fetch reviews for a GBP location. Returns {averageRating, totalReviewCount, reviews: [...]}."""
        creds = await gbp_oauth_service.get_credentials(tenant_id, self.db)
        if not creds:
            return {"reviews": [], "averageRating": 0, "totalReviewCount": 0}

        # Reviews are still on the v4 endpoint
        # location_name format: "accounts/{id}/locations/{id}"
        # For v1, we use the account management location resource
        headers = {"Authorization": f"Bearer {creds.token}"}
        url = f"{GBP_API_BASE}/{location_name}/reviews?pageSize={page_size}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("GBP fetch_reviews failed", status=resp.status_code, body=resp.text[:300])
                return {"reviews": [], "averageRating": 0, "totalReviewCount": 0}
            return resp.json()

    # ── Reply to Review ─────────────────────────────────────────────

    async def reply_to_review(self, tenant_id: str, review_name: str, reply_text: str) -> bool:
        """Post an owner reply to a review."""
        creds = await gbp_oauth_service.get_credentials(tenant_id, self.db)
        if not creds:
            return False

        headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
        url = f"{GBP_API_BASE}/{review_name}/reply"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.put(url, json={"comment": reply_text}, headers=headers)
            if resp.status_code in (200, 201):
                return True
            logger.warning("GBP reply_to_review failed", status=resp.status_code, body=resp.text[:300])
            return False

    # ── Sync Location → DB ──────────────────────────────────────────

    async def sync_location_to_db(self, tenant_id: str, location_data: Dict, account_name: str) -> GBPLocation:
        """Parse GBP location data and upsert into gbp_locations table."""
        name = location_data.get("name", "")  # e.g. "locations/12345"
        title = location_data.get("title", "Unknown")

        addr = location_data.get("storefrontAddress", {})
        address_lines = addr.get("addressLines", [])
        city = addr.get("locality", "")
        state = addr.get("administrativeArea", "")
        zip_code = addr.get("postalCode", "")

        phones = location_data.get("phoneNumbers", {})
        phone = phones.get("primaryPhone", "")

        website = location_data.get("websiteUri", "")

        categories = location_data.get("categories", {})
        primary_cat = categories.get("primaryCategory", {}).get("displayName", "")

        lat = location_data.get("metadata", {}).get("mapsUri", "")  # fallback
        latlng = location_data.get("metadata", {}).get("latlng", {})
        latitude = str(latlng.get("latitude", "")) if latlng else ""
        longitude = str(latlng.get("longitude", "")) if latlng else ""

        # Upsert
        result = await self.db.execute(
            select(GBPLocation).where(GBPLocation.gbp_location_name == name)
        )
        loc = result.scalar_one_or_none()
        if not loc:
            loc = GBPLocation(tenant_id=tenant_id, gbp_location_name=name)
            self.db.add(loc)

        loc.gbp_account_name = account_name
        loc.business_name = title
        loc.address = ", ".join(address_lines) if address_lines else ""
        loc.city = city
        loc.state = state
        loc.zip_code = zip_code
        loc.phone = phone
        loc.website = website
        loc.primary_category = primary_cat
        loc.latitude = latitude
        loc.longitude = longitude

        await self.db.flush()
        return loc

    # ── Sync Reviews → DB ───────────────────────────────────────────

    async def sync_reviews_to_db(self, tenant_id: str, location_id: str, reviews_data: Dict) -> int:
        """Parse GBP reviews and upsert into gbp_reviews table. Returns count synced."""
        reviews = reviews_data.get("reviews", [])
        count = 0
        for r in reviews:
            review_name = r.get("name", "")
            if not review_name:
                continue

            existing = await self.db.execute(
                select(GBPReview).where(GBPReview.gbp_review_name == review_name)
            )
            rev = existing.scalar_one_or_none()
            if not rev:
                rev = GBPReview(
                    tenant_id=tenant_id,
                    location_id=location_id,
                    gbp_review_name=review_name,
                )
                self.db.add(rev)

            reviewer = r.get("reviewer", {})
            rev.reviewer_name = reviewer.get("displayName", "Anonymous")

            # Rating: STAR_RATING_UNSPECIFIED, ONE, TWO, THREE, FOUR, FIVE
            star_map = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
            rev.rating = star_map.get(r.get("starRating", ""), 0)

            rev.comment = r.get("comment", "")
            if r.get("createTime"):
                try:
                    rev.review_time = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00"))
                except Exception:
                    pass

            # Owner reply
            reply = r.get("reviewReply", {})
            if reply:
                rev.has_owner_reply = True
                rev.owner_reply = reply.get("comment", "")

            # Sentiment heuristic
            if rev.rating >= 4:
                rev.sentiment = "positive"
            elif rev.rating == 3:
                rev.sentiment = "neutral"
            else:
                rev.sentiment = "negative"

            count += 1

        await self.db.flush()
        return count

    # ── Auto-Populate BusinessProfile from GBP ──────────────────────

    async def populate_business_profile(self, tenant_id: str, location_data: Dict, reviews_data: Dict) -> None:
        """
        Take GBP location + reviews data and fill in structured fields
        on the BusinessProfile for this tenant.
        """
        result = await self.db.execute(
            select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
        )
        bp = result.scalar_one_or_none()
        if not bp:
            return

        # Address
        addr = location_data.get("storefrontAddress", {})
        address_lines = addr.get("addressLines", [])
        if address_lines and not bp.address:
            bp.address = ", ".join(address_lines)
        if addr.get("locality") and not bp.city:
            bp.city = addr["locality"]
        if addr.get("administrativeArea") and not bp.state:
            bp.state = addr["administrativeArea"]
        if addr.get("postalCode") and not bp.zip_code:
            bp.zip_code = addr["postalCode"]

        # Phone (GBP overrides if not manually set)
        phones = location_data.get("phoneNumbers", {})
        if phones.get("primaryPhone") and not bp.phone:
            bp.phone = phones["primaryPhone"]

        # Website
        if location_data.get("websiteUri") and not bp.website_url:
            bp.website_url = location_data["websiteUri"]

        # Category → industry
        cats = location_data.get("categories", {})
        primary_cat = cats.get("primaryCategory", {}).get("displayName", "")
        if primary_cat:
            bp.primary_category = primary_cat
            if not bp.industry_classification:
                bp.industry_classification = primary_cat

        # Description from profile
        profile_desc = location_data.get("profile", {}).get("description", "")
        if profile_desc and not bp.description:
            bp.description = profile_desc

        # Business hours
        regular_hours = location_data.get("regularHours", {})
        if regular_hours.get("periods"):
            hours_dict = self._parse_hours(regular_hours["periods"])
            bp.business_hours_json = hours_dict

        # Service area
        service_area = location_data.get("serviceArea", {})
        if service_area:
            bp.service_radius_miles = self._parse_service_radius(service_area)

        # GBP place ID
        metadata = location_data.get("metadata", {})
        if metadata.get("placeId"):
            bp.gbp_place_id = metadata["placeId"]

        # Rating & reviews
        avg_rating = reviews_data.get("averageRating", 0)
        total_reviews = reviews_data.get("totalReviewCount", 0)
        if avg_rating:
            bp.google_rating = float(avg_rating)
        if total_reviews:
            bp.review_count = int(total_reviews)

        bp.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        logger.info("BusinessProfile populated from GBP", tenant_id=tenant_id, rating=avg_rating, reviews=total_reviews)

    # ── Helpers ──────────────────────────────────────────────────────

    def _parse_hours(self, periods: List[Dict]) -> Dict[str, str]:
        """Convert GBP regularHours periods to {monday: '8:00-18:00', ...}."""
        day_map = {
            "MONDAY": "monday", "TUESDAY": "tuesday", "WEDNESDAY": "wednesday",
            "THURSDAY": "thursday", "FRIDAY": "friday", "SATURDAY": "saturday",
            "SUNDAY": "sunday",
        }
        hours = {}
        for p in periods:
            day = day_map.get(p.get("openDay", ""), "")
            if not day:
                continue
            open_time = p.get("openTime", {})
            close_time = p.get("closeTime", {})
            oh = f"{open_time.get('hours', 0):02d}:{open_time.get('minutes', 0):02d}"
            ch = f"{close_time.get('hours', 0):02d}:{close_time.get('minutes', 0):02d}"
            if day in hours:
                hours[day] += f", {oh}-{ch}"
            else:
                hours[day] = f"{oh}-{ch}"
        return hours

    def _parse_service_radius(self, service_area: Dict) -> Optional[int]:
        """Extract service radius from GBP serviceArea field."""
        # businessType=CUSTOMER_AND_SERVICE_AREA or SERVICE_AREA_BUSINESS
        radius = service_area.get("radius", {})
        if radius:
            value = radius.get("radiusKm", 0) or radius.get("latlng", {})
            if isinstance(value, (int, float)) and value > 0:
                return int(value * 0.621371)  # km → miles
        # places-based service area: just return None for now
        return None
