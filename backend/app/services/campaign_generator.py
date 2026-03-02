"""
Prompt-to-Campaign Generator Service

Pipeline:
1) Parse intent from prompt (service, geo, offer, objective)
2) Pull business profile + best past performance patterns
3) Pull existing account structure to avoid duplicates
4) Propose campaign type (Search, Call, PMax, Remarketing)
5) Create full draft with all entities
6) Return preview for approval
"""
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.business_profile import BusinessProfile
from app.models.campaign import Campaign
from app.models.playbook import Playbook
from app.models.learning import Learning


class CampaignGeneratorService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def generate_from_prompt(
        self,
        prompt: str,
        business_profile: BusinessProfile,
        google_customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        intent = self._parse_intent(prompt, business_profile)
        campaign_type = self._determine_campaign_type(intent, business_profile)
        existing = await self._get_existing_campaigns()
        playbook = await self._get_playbook(business_profile.industry_classification, intent.get("goal"))
        learnings = await self._get_relevant_learnings(business_profile.industry_classification)

        draft = self._build_campaign_draft(
            intent=intent,
            campaign_type=campaign_type,
            business_profile=business_profile,
            existing_campaigns=existing,
            playbook=playbook,
            learnings=learnings,
            google_customer_id=google_customer_id,
        )
        return draft

    def _parse_intent(self, prompt: str, profile: BusinessProfile) -> Dict[str, Any]:
        prompt_lower = prompt.lower()
        intent = {
            "raw_prompt": prompt,
            "services": [],
            "locations": [],
            "offers": [],
            "objective": profile.primary_conversion_goal or "calls",
            "urgency": "normal",
            "goal": "leads",
        }

        services = profile.services_json if isinstance(profile.services_json, list) else profile.services_json.get("list", [])
        for svc in services:
            svc_name = svc if isinstance(svc, str) else svc.get("name", "")
            if svc_name.lower() in prompt_lower:
                intent["services"].append(svc_name)

        if not intent["services"] and services:
            intent["services"] = [s if isinstance(s, str) else s.get("name", "") for s in services[:3]]

        locations = profile.locations_json if isinstance(profile.locations_json, list) else profile.locations_json.get("cities", [])
        for loc in locations:
            loc_name = loc if isinstance(loc, str) else loc.get("name", "")
            if loc_name.lower() in prompt_lower:
                intent["locations"].append(loc_name)
        if not intent["locations"] and locations:
            intent["locations"] = [l if isinstance(l, str) else l.get("name", "") for l in locations[:5]]

        emergency_keywords = ["emergency", "urgent", "24/7", "same day", "asap", "fast"]
        if any(kw in prompt_lower for kw in emergency_keywords):
            intent["urgency"] = "high"

        offers = profile.offers_json if isinstance(profile.offers_json, list) else profile.offers_json.get("list", [])
        for offer in offers:
            offer_text = offer if isinstance(offer, str) else offer.get("text", "")
            if offer_text.lower() in prompt_lower:
                intent["offers"].append(offer_text)

        if "remarketing" in prompt_lower or "retarget" in prompt_lower:
            intent["goal"] = "remarketing"
        elif "brand" in prompt_lower or "awareness" in prompt_lower:
            intent["goal"] = "awareness"
        elif "call" in prompt_lower:
            intent["goal"] = "calls"

        return intent

    def _determine_campaign_type(self, intent: Dict, profile: BusinessProfile) -> str:
        if intent.get("goal") == "remarketing":
            return "REMARKETING"
        if intent.get("goal") == "awareness":
            return "PERFORMANCE_MAX"
        if intent.get("urgency") == "high" or profile.primary_conversion_goal == "calls":
            return "CALL"
        return "SEARCH"

    async def _get_existing_campaigns(self) -> List[Dict]:
        result = await self.db.execute(
            select(Campaign).where(Campaign.tenant_id == self.tenant_id)
        )
        campaigns = result.scalars().all()
        return [{"name": c.name, "type": c.type, "status": c.status} for c in campaigns]

    async def _get_playbook(self, industry: Optional[str], goal: Optional[str]) -> Optional[Dict]:
        if not industry:
            return None
        result = await self.db.execute(
            select(Playbook).where(
                Playbook.industry == industry,
                Playbook.goal_type == (goal or "leads"),
            )
        )
        pb = result.scalar_one_or_none()
        return pb.template_json if pb else None

    async def _get_relevant_learnings(self, industry: Optional[str]) -> List[Dict]:
        if not industry:
            return []
        result = await self.db.execute(
            select(Learning).where(Learning.industry == industry, Learning.confidence >= 0.5)
        )
        learnings = result.scalars().all()
        return [{"type": l.pattern_type, "pattern": l.pattern_json, "confidence": l.confidence} for l in learnings]

    def _build_campaign_draft(
        self,
        intent: Dict,
        campaign_type: str,
        business_profile: BusinessProfile,
        existing_campaigns: List[Dict],
        playbook: Optional[Dict],
        learnings: List[Dict],
        google_customer_id: Optional[str],
    ) -> Dict[str, Any]:
        services = intent.get("services", ["General Service"])
        locations = intent.get("locations", [])
        offers = intent.get("offers", [])
        phone = business_profile.phone or ""
        website = business_profile.website_url or ""
        industry = business_profile.industry_classification or "general"
        brand_voice = business_profile.brand_voice_json or {}
        tone = brand_voice.get("tone", "professional")

        primary_service = services[0] if services else "Service"
        campaign_name = f"{primary_service} - {campaign_type} - {'Emergency' if intent.get('urgency') == 'high' else 'Standard'}"

        existing_names = {c["name"] for c in existing_campaigns}
        if campaign_name in existing_names:
            campaign_name = f"{campaign_name} ({str(uuid.uuid4())[:4]})"

        ad_groups = []
        for svc in services:
            keywords = self._generate_keywords(svc, locations, industry, learnings)
            negatives = self._generate_negatives(industry, learnings)
            headlines = self._generate_headlines(svc, locations, offers, phone, tone, industry)
            descriptions = self._generate_descriptions(svc, locations, offers, phone, tone, industry)

            ad_group = {
                "name": f"{svc} - {'|'.join(locations[:2]) if locations else 'All Areas'}",
                "keywords": keywords,
                "negatives": negatives,
                "ads": [
                    {
                        "type": "RESPONSIVE_SEARCH_AD",
                        "headlines": headlines,
                        "descriptions": descriptions,
                        "final_urls": [f"{website}/{svc.lower().replace(' ', '-')}"] if website else [website],
                    }
                ],
            }
            ad_groups.append(ad_group)

        extensions = self._generate_extensions(business_profile, services, offers)

        budget_micros = 30_000_000
        if playbook and "default_budget_micros" in playbook:
            budget_micros = playbook["default_budget_micros"]

        bidding = "MAXIMIZE_CONVERSIONS"
        if campaign_type == "CALL":
            bidding = "MAXIMIZE_CONVERSIONS"
        elif campaign_type == "PERFORMANCE_MAX":
            bidding = "MAXIMIZE_CONVERSION_VALUE"

        return {
            "campaign": {
                "name": campaign_name,
                "type": campaign_type,
                "objective": intent.get("goal", "leads"),
                "budget_micros": budget_micros,
                "budget_daily": budget_micros / 1_000_000,
                "bidding_strategy": bidding,
                "locations": locations,
                "schedule": {"all_day": True},
                "settings": {
                    "network": "SEARCH" if campaign_type == "SEARCH" else "ALL",
                    "language": "en",
                },
            },
            "ad_groups": ad_groups,
            "extensions": extensions,
            "intent": intent,
            "reasoning": {
                "campaign_type_reason": self._explain_campaign_type(campaign_type, intent),
                "keyword_strategy": "Exact + Phrase match for high intent, limited broad with safeguards",
                "playbook_used": playbook is not None,
                "learnings_applied": len(learnings),
            },
        }

    def _generate_keywords(self, service: str, locations: List[str], industry: str, learnings: List[Dict]) -> List[Dict]:
        base_keywords = [
            {"text": service.lower(), "match_type": "PHRASE"},
            {"text": f"{service.lower()} near me", "match_type": "EXACT"},
            {"text": f"{service.lower()} service", "match_type": "PHRASE"},
            {"text": f"best {service.lower()}", "match_type": "PHRASE"},
            {"text": f"affordable {service.lower()}", "match_type": "PHRASE"},
            {"text": f"professional {service.lower()}", "match_type": "EXACT"},
        ]

        if industry == "locksmith":
            base_keywords.extend([
                {"text": f"emergency {service.lower()}", "match_type": "EXACT"},
                {"text": f"24 hour {service.lower()}", "match_type": "EXACT"},
                {"text": f"locked out {service.lower()}", "match_type": "PHRASE"},
            ])
        elif industry == "roofing":
            base_keywords.extend([
                {"text": f"roof repair {service.lower()}", "match_type": "EXACT"},
                {"text": f"storm damage {service.lower()}", "match_type": "PHRASE"},
            ])
        elif industry == "auto_repair":
            base_keywords.extend([
                {"text": f"auto {service.lower()}", "match_type": "PHRASE"},
                {"text": f"car {service.lower()}", "match_type": "PHRASE"},
            ])

        for loc in locations[:3]:
            base_keywords.append({"text": f"{service.lower()} {loc.lower()}", "match_type": "EXACT"})
            base_keywords.append({"text": f"{service.lower()} in {loc.lower()}", "match_type": "PHRASE"})

        for learning in learnings:
            if learning["type"] == "headline_theme" and "keywords" in learning.get("pattern", {}):
                for kw in learning["pattern"]["keywords"][:3]:
                    base_keywords.append({"text": kw, "match_type": "PHRASE"})

        return base_keywords

    def _generate_negatives(self, industry: str, learnings: List[Dict]) -> List[Dict]:
        universal_negatives = [
            "free", "diy", "how to", "youtube", "reddit", "wiki",
            "salary", "jobs", "hiring", "career", "training", "course",
            "complaint", "lawsuit", "scam",
        ]

        industry_negatives = {
            "locksmith": ["locksmith training", "locksmith tools", "lock picking set"],
            "roofing": ["roofing materials wholesale", "roofing jobs", "roofing nails"],
            "auto_repair": ["auto parts", "car parts online", "junkyard"],
            "hvac": ["hvac certification", "hvac school", "hvac tools"],
            "plumbing": ["plumbing supplies", "plumbing code", "plumbing school"],
        }

        negatives = [{"text": n, "match_type": "PHRASE"} for n in universal_negatives]
        for n in industry_negatives.get(industry, []):
            negatives.append({"text": n, "match_type": "EXACT"})

        for learning in learnings:
            if learning["type"] == "negative_base" and "negatives" in learning.get("pattern", {}):
                for neg in learning["pattern"]["negatives"][:5]:
                    negatives.append({"text": neg, "match_type": "PHRASE"})

        return negatives

    def _generate_headlines(self, service: str, locations: List[str], offers: List[str], phone: str, tone: str, industry: str) -> List[str]:
        headlines = [
            f"{service} Experts Near You",
            f"Professional {service}",
            f"Trusted {service} Service",
            f"Licensed & Insured {service}",
            f"Top-Rated {service}",
            f"Fast & Reliable {service}",
            f"Call Now for {service}",
            f"{service} - Same Day",
            f"Quality {service} Guaranteed",
            f"Affordable {service} Rates",
        ]

        if locations:
            headlines.append(f"{service} in {locations[0]}")
            headlines.append(f"{locations[0]} {service} Pros")

        if offers:
            headlines.append(offers[0][:30])

        if phone:
            headlines.append(f"Call {phone}")

        if tone == "urgent" or industry == "locksmith":
            headlines.extend(["24/7 Emergency Service", "Fast Response Guaranteed"])

        return headlines[:15]

    def _generate_descriptions(self, service: str, locations: List[str], offers: List[str], phone: str, tone: str, industry: str) -> List[str]:
        descriptions = [
            f"Professional {service} services you can trust. Licensed, insured & experienced. Call today for a free estimate!",
            f"Looking for reliable {service}? Our experts deliver quality results at competitive prices. Satisfaction guaranteed.",
            f"Top-rated {service} provider serving your area. Fast response, fair pricing, and exceptional service every time.",
            f"Don't settle for less. Choose our {service} team for dependable, high-quality work. Free quotes available!",
        ]

        if locations:
            descriptions.append(f"Proudly serving {', '.join(locations[:3])} and surrounding areas. Call now for {service.lower()}!")

        if offers:
            descriptions.append(f"{offers[0]}. Contact us today for professional {service.lower()} you can rely on!")

        return descriptions[:6]

    def _generate_extensions(self, profile: BusinessProfile, services: List[str], offers: List[str]) -> Dict[str, Any]:
        sitelinks = [
            {"text": "Our Services", "description": f"View all {profile.industry_classification or 'services'} we offer", "url": f"{profile.website_url}/services"},
            {"text": "About Us", "description": "Learn about our team and experience", "url": f"{profile.website_url}/about"},
            {"text": "Contact Us", "description": "Get in touch for a free estimate", "url": f"{profile.website_url}/contact"},
            {"text": "Reviews", "description": "See what our customers say", "url": f"{profile.website_url}/reviews"},
        ]

        callouts = [
            "Licensed & Insured",
            "Free Estimates",
            "Satisfaction Guaranteed",
            "Experienced Professionals",
            "Locally Owned",
            "Fast Response",
            "Competitive Pricing",
            "Same Day Service",
        ]

        structured_snippets = [
            {"header": "Services", "values": services[:5]},
        ]

        result = {
            "sitelinks": sitelinks,
            "callouts": callouts,
            "structured_snippets": structured_snippets,
        }

        if profile.phone:
            result["call_extension"] = {"phone": profile.phone}

        return result

    def _explain_campaign_type(self, campaign_type: str, intent: Dict) -> str:
        reasons = {
            "SEARCH": "Search campaigns target high-intent users actively looking for your services.",
            "CALL": "Call campaigns are ideal for emergency/urgent services where phone calls drive conversions.",
            "PERFORMANCE_MAX": "Performance Max provides broader local presence across Google's networks.",
            "REMARKETING": "Remarketing re-engages users who previously visited your site.",
        }
        return reasons.get(campaign_type, "Selected based on business profile and intent analysis.")
