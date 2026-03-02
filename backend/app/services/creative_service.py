"""
Creative Service — Ad copy generation and brand kit management.
"""
from typing import Optional, Dict, Any, List
from app.models.business_profile import BusinessProfile


class CreativeService:
    def __init__(self, profile: Optional[BusinessProfile] = None):
        self.profile = profile

    def generate_ad_copy(
        self,
        service: Optional[str] = None,
        location: Optional[str] = None,
        offer: Optional[str] = None,
        tone: Optional[str] = None,
        count: int = 10,
    ) -> Dict[str, Any]:
        svc = service or "Our Services"
        loc = location or ""
        brand = self.profile.brand_voice_json if self.profile else {}
        effective_tone = tone or brand.get("tone", "professional")

        headlines = self._gen_headlines(svc, loc, offer, effective_tone, count)
        descriptions = self._gen_descriptions(svc, loc, offer, effective_tone, min(count, 6))
        callouts = self._gen_callouts(svc, effective_tone, 8)
        sitelinks = self._gen_sitelinks(svc, 4)

        return {
            "headlines": headlines,
            "descriptions": descriptions,
            "callouts": callouts,
            "sitelinks": sitelinks,
            "tone_used": effective_tone,
            "service": svc,
            "location": loc,
        }

    def _gen_headlines(self, svc: str, loc: str, offer: Optional[str], tone: str, count: int) -> List[str]:
        base = [
            f"{svc} Experts",
            f"Professional {svc}",
            f"Top-Rated {svc}",
            f"Trusted {svc} Pros",
            f"Quality {svc} Service",
            f"{svc} You Can Trust",
            f"Licensed {svc} Team",
            f"Reliable {svc}",
            f"Award-Winning {svc}",
            f"Best {svc} Near You",
            f"Fast & Affordable {svc}",
            f"{svc} Done Right",
            f"Expert {svc} Help",
            f"Your {svc} Specialists",
            f"Guaranteed {svc}",
        ]
        if loc:
            base.extend([f"{svc} in {loc}", f"{loc} {svc} Pros", f"Serving {loc} Area"])
        if offer:
            base.append(offer[:30])
        if tone == "urgent":
            base.extend(["24/7 Emergency Service", "Call Now - Fast Response", "Same Day Available"])
        elif tone == "premium":
            base.extend(["Premium Quality Service", "Luxury Service Experience", "Excellence Guaranteed"])
        elif tone == "budget":
            base.extend(["Lowest Price Guarantee", "Budget-Friendly Rates", "Affordable Excellence"])

        return base[:count]

    def _gen_descriptions(self, svc: str, loc: str, offer: Optional[str], tone: str, count: int) -> List[str]:
        base = [
            f"Professional {svc.lower()} services delivered with expertise and care. Licensed, insured, and ready to help. Call today!",
            f"Looking for dependable {svc.lower()}? Our certified team provides top-quality work at fair prices. Free estimates available.",
            f"Trust the {svc.lower()} experts. Years of experience, thousands of satisfied customers. Satisfaction guaranteed every time.",
            f"Don't wait — get reliable {svc.lower()} from a team that cares. Quick response, quality work, competitive rates.",
            f"Experience the difference with our {svc.lower()} services. Fully licensed, insured, and committed to your satisfaction.",
            f"Need {svc.lower()} help? Our skilled professionals are standing by. Call now for a no-obligation consultation!",
        ]
        if loc:
            base.append(f"Proudly serving {loc} and surrounding communities. Contact us for expert {svc.lower()} today!")
        if offer:
            base.append(f"Special offer: {offer}. Professional {svc.lower()} at unbeatable value. Limited time — call now!")
        return base[:count]

    def _gen_callouts(self, svc: str, tone: str, count: int) -> List[str]:
        base = [
            "Licensed & Insured",
            "Free Estimates",
            "Satisfaction Guaranteed",
            "Experienced Professionals",
            "Locally Owned & Operated",
            "Fast Response Times",
            "Competitive Pricing",
            "Same Day Service",
            "5-Star Reviews",
            "No Hidden Fees",
        ]
        if tone == "urgent":
            base.extend(["24/7 Availability", "Emergency Service"])
        return base[:count]

    def _gen_sitelinks(self, svc: str, count: int) -> List[Dict[str, str]]:
        website = self.profile.website_url if self.profile else "https://example.com"
        return [
            {"text": "Our Services", "description": f"Full range of {svc.lower()} services", "url": f"{website}/services"},
            {"text": "Free Estimate", "description": "Get your no-obligation quote today", "url": f"{website}/contact"},
            {"text": "About Us", "description": "Meet our experienced team", "url": f"{website}/about"},
            {"text": "Testimonials", "description": "Read what customers are saying", "url": f"{website}/reviews"},
        ][:count]
